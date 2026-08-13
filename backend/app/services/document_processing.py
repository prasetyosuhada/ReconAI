"""Background service for document intake & bookkeeping processing."""

import logging
import uuid
from datetime import date, datetime
from typing import Any

from app.agents.orchestrator import document_processing_graph
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.review import ReviewItem
from app.services.accounting import save_journal_entry_safely
from app.services.document_extraction import extract_document_content

logger = logging.getLogger(__name__)


def _parse_date(d: Any) -> date | None:
    """Safely parse date from date object, datetime object, or string."""
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str) and len(d) >= 10:
        try:
            return datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def process_document_background(
    document_id: str | uuid.UUID,
    stored_file_path: str,
    mime_type: str,
    original_filename: str,
    document_type: str = "unknown",
) -> None:
    """Execute LangGraph document intake & bookkeeping workflow asynchronously.

    Args:
        document_id: UUID object or UUID string of Document record.
        stored_file_path: Absolute disk path where uploaded file is stored.
        mime_type: File content-type (e.g. application/pdf, image/png).
        original_filename: Original name of the uploaded file.
        document_type: Document classification e.g. invoice, receipt, unknown.
    """
    logger.info("Starting background processing for document ID: %s", document_id)
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        if not doc:
            logger.error(
                "Document %s not found in DB during background processing.",
                document_id,
            )
            return

        doc.status = "extracting"
        db.commit()

        # Extract text / image content from the uploaded file before LLM
        raw_text, _image_b64 = extract_document_content(
            file_path=stored_file_path,
            mime_type=mime_type,
        )

        logger.info(
            "Document %s: extracted %d chars of raw text from %s",
            document_id,
            len(raw_text),
            original_filename,
        )

        # Load active Chart of Accounts from DB to provide context to Bookkeeping Agent
        coa_rows = (
            db.query(ChartOfAccount)
            .filter(ChartOfAccount.is_active == True)  # noqa: E712
            .order_by(ChartOfAccount.account_code)
            .all()
        )
        coa_list = [
            {
                "account_code": coa.account_code,
                "account_name": coa.account_name,
                "account_type": coa.account_type,
                "normal_balance": coa.normal_balance,
                "is_sensitive": coa.is_sensitive,
                "description": coa.description,
            }
            for coa in coa_rows
        ]
        logger.info(
            "Document %s: loaded %d active COA entries from DB.",
            document_id,
            len(coa_list),
        )

        initial_state: dict[str, Any] = {
            "document_id": str(doc_uuid),
            "original_filename": original_filename,
            "mime_type": mime_type,
            "stored_file_path": stored_file_path,
            "raw_text": raw_text or None,
            "status": "extracting",
            "chart_of_accounts": coa_list,
        }
        print("INITIAL STATE:\n", initial_state)

        # Run compiled LangGraph StateGraph workflow
        final_state = document_processing_graph.invoke(initial_state)
        print("HASIL INVOKE:\n", final_state)

        final_status = final_state.get("status", "extracted")
        confidence_score = final_state.get("confidence_score", 0.0)
        needs_review = final_state.get("needs_review", False)
        risk_flags = final_state.get("risk_flags", [])

        # 1. Save DocumentExtraction record in DB
        extraction = DocumentExtraction(
            id=uuid.uuid4(),
            document_id=doc.id,
            vendor_name=final_state.get("vendor_name"),
            transaction_date=_parse_date(final_state.get("transaction_date")),
            subtotal_amount=final_state.get("subtotal_amount"),
            tax_amount=final_state.get("tax_amount"),
            total_amount=final_state.get("total_amount"),
            currency=final_state.get("currency", "IDR"),
            line_items=final_state.get("line_items", []),
            raw_text=final_state.get("raw_text"),
            confidence_score=confidence_score,
            rationale=final_state.get("rationale"),
            status="extracted" if not needs_review else "draft",
        )
        db.add(extraction)
        db.commit()
        db.refresh(extraction)

        # 2. Save Proposed Journal Entry using deterministic guardrails
        proposed_journal = (
            final_state.get("journal_entry")
            or final_state.get("proposed_journal")
            or final_state.get("journal_lines")
        )
        print("PROPOSED JOURNAL:\n", proposed_journal)
        saved_journal_id = None

        if proposed_journal:
            vendor = final_state.get("vendor_name", "Vendor")
            journal_desc = f"Journal for {original_filename} ({vendor})"
            journal_data = {
                "document_id": doc.id,
                "extraction_id": extraction.id,
                "entry_date": _parse_date(final_state.get("transaction_date"))
                or date.today(),
                "description": journal_desc,
                "status": "review_required" if needs_review else "draft",
                "agent_name": "BookkeepingAgent",
                "confidence_score": confidence_score,
                "rationale": final_state.get("rationale"),
                "risk_flags": risk_flags,
                "lines": proposed_journal,
            }
            save_res = save_journal_entry_safely(journal_data, db_session=db)
            if save_res.success:
                saved_journal_id = save_res.journal_entry_id

        # 3. Handle Human-in-the-Loop Review Queue
        review_item_created = False

        if (
            needs_review
            or final_status
            in ("extraction_review_required", "bookkeeping_review_required")
            or risk_flags
        ):
            review_type = (
                "extraction"
                if final_status == "extraction_review_required"
                else "bookkeeping"
            )
            is_balanced = final_state.get("is_balanced", True)
            is_sensitive = "uses_sensitive_account" in risk_flags
            priority = "high" if is_sensitive or not is_balanced else "normal"

            flags_str = ", ".join(risk_flags) if risk_flags else "None"
            review_summary = (
                f"Agent flagged document. Conf: {confidence_score:.2f}, "
                f"Flags: {flags_str}"
            )

            review_item = ReviewItem(
                id=uuid.uuid4(),
                review_type=review_type,
                status="pending",
                priority=priority,
                source_type="document",
                source_id=doc.id,
                title=f"Review Needed: {original_filename}",
                summary=review_summary,
                suggested_action="Review extracted data and journal lines.",
                original_payload=dict(final_state),
            )
            db.add(review_item)
            review_item_created = True

        doc.status = final_status
        db.commit()

        # 4. Audit Trail Event
        audit = AuditEvent(
            event_type="extraction_completed",
            source_type="document",
            source_id=doc.id,
            actor_type="agent",
            actor_name="DocumentProcessingGraph",
            input_snapshot={
                "document_id": str(doc_uuid),
                "original_filename": original_filename,
            },
            output_snapshot={
                "status": final_status,
                "confidence_score": confidence_score,
                "needs_review": needs_review,
                "extraction_id": str(extraction.id),
                "journal_entry_id": saved_journal_id,
                "review_item_created": review_item_created,
            },
            confidence_score=confidence_score,
            rationale=final_state.get("rationale"),
        )
        db.add(audit)
        db.commit()

        logger.info(
            "Completed background document processing for %s, status: %s",
            document_id,
            final_status,
        )

    except Exception as e:
        logger.error(
            "Error processing document %s in background: %s",
            document_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        try:
            doc = db.query(Document).filter(Document.id == doc_uuid).first()
            if doc:
                doc.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
