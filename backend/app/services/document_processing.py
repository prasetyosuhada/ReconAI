import json
import logging
import uuid
from collections.abc import Generator
from datetime import date, datetime
from typing import Any

from app.agents.orchestrator import document_processing_graph
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.accounting import save_journal_entry_safely
from app.services.audit_service import log_event
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


def stream_document_processing(
    document_id: str | uuid.UUID,
    stored_file_path: str | None = None,
    mime_type: str | None = None,
    original_filename: str | None = None,
    document_type: str = "unknown",
) -> Generator[str, None, None]:
    """Execute LangGraph document intake & bookkeeping workflow and yield real-time SSE events."""
    logger.info("Starting streaming document processing for document ID: %s", document_id)
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        if not doc:
            logger.error("Document %s not found in DB.", document_id)
            yield f"data: {json.dumps({'stage': 'error', 'message': f'Document [{document_id}] not found.'})}\n\n"
            return

        # Guard against duplicate concurrent execution or re-execution of already-completed documents
        if doc.status in (
            "extracted",
            "ready_to_post",
            "review_required",
            "extraction_review_required",
            "bookkeeping_review_required",
        ):
            logger.info(
                "Document %s already processed (status=%s). Returning existing results.",
                document_id,
                doc.status,
            )
            existing_extraction = (
                db.query(DocumentExtraction)
                .filter(DocumentExtraction.document_id == doc.id)
                .first()
            )
            vendor = (
                existing_extraction.vendor_name
                if existing_extraction
                else "Document"
            )
            tot_amount = (
                float(existing_extraction.total_amount)
                if existing_extraction and existing_extraction.total_amount
                else 0.0
            )
            curr = existing_extraction.currency if existing_extraction else "IDR"
            conf = (
                float(existing_extraction.confidence_score)
                if existing_extraction
                else 1.0
            )
            yield f"data: {json.dumps({'stage': 'completed', 'percentage': 100, 'status': doc.status, 'confidence_score': conf, 'vendor_name': vendor, 'total_amount': tot_amount, 'currency': curr, 'message': f'Document \"{doc.original_filename}\" is already processed.'})}\n\n"
            return

        file_path = stored_file_path or doc.stored_file_path
        effective_mime = mime_type or doc.mime_type
        fname = original_filename or doc.original_filename

        doc.status = "extracting"
        db.commit()

        yield f"data: {json.dumps({'stage': 'init', 'percentage': 10, 'message': f'Document Intake pipeline initialized for \"{fname}\"...'})}\n\n"

        # Step 1: Text & OCR Extraction
        yield f"data: {json.dumps({'stage': 'ocr_started', 'percentage': 25, 'message': f'Extracting text & visual tokens via OCR parser ({effective_mime})...'})}\n\n"

        raw_text, _image_b64 = extract_document_content(
            file_path=file_path,
            mime_type=effective_mime,
        )

        char_count = len(raw_text) if raw_text else 0
        yield f"data: {json.dumps({'stage': 'ocr_extracted', 'percentage': 40, 'message': f'Extracted {char_count} characters of content from file.', 'text_preview': (raw_text[:180] + '...') if raw_text else None})}\n\n"

        # Step 2: Load Active COA
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

        yield f"data: {json.dumps({'stage': 'coa_loaded', 'percentage': 50, 'message': f'Loaded {len(coa_list)} Chart of Accounts entries for AI classifier.'})}\n\n"

        # Step 3: Stream LangGraph execution (Document Intake Agent -> Bookkeeping Agent)
        yield f"data: {json.dumps({'stage': 'intake_agent', 'percentage': 55, 'message': 'Invoking Document Intake Agent (Gemini 3 Flash) for entity extraction...'})}\n\n"

        initial_state: dict[str, Any] = {
            "document_id": str(doc_uuid),
            "original_filename": fname,
            "mime_type": effective_mime,
            "stored_file_path": file_path,
            "raw_text": raw_text or None,
            "status": "extracting",
            "chart_of_accounts": coa_list,
        }

        final_state: dict[str, Any] = dict(initial_state)

        for step_output in document_processing_graph.stream(initial_state):
            print("STEP OUTPUT:\n", step_output)
            # 1. Document Intake Agent Node
            if "document_intake" in step_output:
                intake_data = step_output["document_intake"]
                final_state.update(intake_data)
                vendor = intake_data.get("vendor_name") or "Unknown Vendor"
                tot_amount = intake_data.get("total_amount")
                curr = intake_data.get("currency", "IDR")
                conf = float(intake_data.get("confidence_score", 0.0))
                needs_rev = intake_data.get("needs_review", False)

                yield f"data: {json.dumps({'stage': 'intake_done', 'percentage': 70, 'vendor_name': vendor, 'total_amount': tot_amount, 'currency': curr, 'confidence_score': conf, 'message': f'✓ Document Intake Agent: Extracted {vendor} • {curr} {tot_amount or 0:,.0f} (Confidence: {int(conf * 100)}%)'})}\n\n"

                if not needs_rev:
                    yield f"data: {json.dumps({'stage': 'bookkeeping_agent', 'percentage': 75, 'message': 'Invoking Bookkeeping Agent (Gemini 3 Flash) for Chart of Accounts classification...'})}\n\n"

            # 2. Bookkeeping Agent Node
            if "bookkeeping" in step_output:
                bookkeeping_data = step_output["bookkeeping"]
                final_state.update(bookkeeping_data)
                lines = bookkeeping_data.get("journal_lines") or []
                is_bal = bookkeeping_data.get("is_balanced", True)
                uses_sens = bookkeeping_data.get("uses_sensitive_account", False)
                bk_conf = float(bookkeeping_data.get("confidence_score", 0.0))

                yield f"data: {json.dumps({'stage': 'bookkeeping_done', 'percentage': 88, 'lines_count': len(lines), 'message': f'✓ Bookkeeping Agent: Classified {len(lines)} journal entry lines (Balanced: {is_bal}, Sensitive: {uses_sens})'})}\n\n"

            # 3. Review Router Node (if routed)
            if "review_router" in step_output:
                router_data = step_output["review_router"]
                final_state.update(router_data)
                yield f"data: {json.dumps({'stage': 'review_queued', 'percentage': 92, 'message': '⚠️ Low confidence or sensitive account flagged. Routing to Human Review Queue.'})}\n\n"

        vendor = final_state.get("vendor_name") or "Unknown Vendor"
        tot_amount = final_state.get("total_amount")
        curr = final_state.get("currency", "IDR")
        final_confidence = float(final_state.get("confidence_score", 0.0))
        final_status = final_state.get("status", "extracted")
        needs_review = final_state.get("needs_review", False)
        final_risk_flags = final_state.get("risk_flags", []) or []
        final_rationale = final_state.get("rationale")

        # 1. Save DocumentExtraction record in DB (idempotent upsert)
        existing_extraction = (
            db.query(DocumentExtraction)
            .filter(DocumentExtraction.document_id == doc.id)
            .first()
        )
        if existing_extraction:
            extraction = existing_extraction
            extraction.vendor_name = final_state.get("vendor_name")
            extraction.transaction_date = _parse_date(
                final_state.get("transaction_date")
            )
            extraction.subtotal_amount = final_state.get("subtotal_amount")
            extraction.tax_amount = final_state.get("tax_amount")
            extraction.total_amount = final_state.get("total_amount")
            extraction.currency = final_state.get("currency", "IDR")
            extraction.line_items = final_state.get("line_items", [])
            extraction.raw_text = final_state.get("raw_text")
            extraction.confidence_score = final_confidence
            extraction.rationale = final_rationale
            extraction.status = "extracted" if not needs_review else "draft"
        else:
            extraction = DocumentExtraction(
                id=uuid.uuid4(),
                document_id=doc.id,
                vendor_name=final_state.get("vendor_name"),
                transaction_date=_parse_date(
                    final_state.get("transaction_date")
                ),
                subtotal_amount=final_state.get("subtotal_amount"),
                tax_amount=final_state.get("tax_amount"),
                total_amount=final_state.get("total_amount"),
                currency=final_state.get("currency", "IDR"),
                line_items=final_state.get("line_items", []),
                raw_text=final_state.get("raw_text"),
                confidence_score=final_confidence,
                rationale=final_rationale,
                status="extracted" if not needs_review else "draft",
            )
            db.add(extraction)

        db.commit()
        db.refresh(extraction)

        # 2. Save Proposed Journal Entry using deterministic guardrails (idempotent check)
        proposed_journal = (
            final_state.get("journal_entry")
            or final_state.get("proposed_journal")
            or final_state.get("journal_lines")
        )
        saved_journal_id = None
        journal_desc = f"Journal for {fname} ({vendor})"
        journal_entry_date = (
            _parse_date(final_state.get("transaction_date")) or date.today()
        )

        existing_je = (
            db.query(JournalEntry)
            .filter(JournalEntry.document_id == doc.id)
            .first()
        )

        if existing_je:
            saved_journal_id = str(existing_je.id)
            logger.info(
                "JournalEntry already exists for document %s (#JE-%s). Skipping duplicate insert.",
                doc.id,
                saved_journal_id[:8],
            )
        elif proposed_journal:
            journal_data = {
                "document_id": doc.id,
                "extraction_id": extraction.id,
                "entry_date": journal_entry_date,
                "description": journal_desc,
                "status": "review_required" if needs_review else "draft",
                "agent_name": "BookkeepingAgent",
                "confidence_score": final_confidence,
                "rationale": final_rationale,
                "risk_flags": final_risk_flags,
                "lines": proposed_journal,
            }
            save_res = save_journal_entry_safely(journal_data, db_session=db)
            if save_res.success:
                saved_journal_id = save_res.journal_entry_id

        # 3. Handle Human-in-the-Loop Review Queue (idempotent check)
        review_item_created = False

        if (
            needs_review
            or final_status
            in (
                "extraction_review_required",
                "bookkeeping_review_required",
            )
            or final_risk_flags
        ):
            review_type = (
                "extraction"
                if final_status == "extraction_review_required"
                else "bookkeeping"
            )
            is_balanced = final_state.get("is_balanced", True)
            is_sensitive = "uses_sensitive_account" in final_risk_flags
            priority = "high" if is_sensitive or not is_balanced else "normal"

            flags_str = (
                ", ".join(final_risk_flags) if final_risk_flags else "None"
            )
            review_summary = f"Agent flagged document. Conf: {final_confidence:.2f}, Flags: {flags_str}"

            if review_type == "bookkeeping" and saved_journal_id:
                review_payload: dict = {
                    "journal_entry_id": str(saved_journal_id),
                    "vendor_name": final_state.get("vendor_name"),
                    "transaction_date": str(
                        final_state.get("transaction_date") or ""
                    ),
                    "total_amount": final_state.get("total_amount"),
                    "subtotal_amount": final_state.get("subtotal_amount"),
                    "tax_amount": final_state.get("tax_amount"),
                    "currency": final_state.get("currency", "IDR"),
                    "line_items": final_state.get("line_items", []),
                    "lines": proposed_journal,
                    "entry_date": str(journal_entry_date),
                    "description": journal_desc,
                    "rationale": final_rationale,
                    "risk_flags": final_risk_flags,
                    "confidence_score": final_confidence,
                    "is_balanced": final_state.get("is_balanced", True),
                    "uses_sensitive_account": final_state.get(
                        "uses_sensitive_account", False
                    ),
                }
                review_source_type = "journal_entry"
                review_source_id = (
                    uuid.UUID(saved_journal_id)
                    if isinstance(saved_journal_id, str)
                    else saved_journal_id
                )
            else:
                review_payload = {
                    "vendor_name": final_state.get("vendor_name"),
                    "transaction_date": str(
                        final_state.get("transaction_date") or ""
                    ),
                    "total_amount": final_state.get("total_amount"),
                    "subtotal_amount": final_state.get("subtotal_amount"),
                    "tax_amount": final_state.get("tax_amount"),
                    "currency": final_state.get("currency", "IDR"),
                    "line_items": final_state.get("line_items", []),
                    "raw_text": final_state.get("raw_text"),
                    "extraction_notes": final_state.get("extraction_notes"),
                    "rationale": final_rationale,
                    "risk_flags": final_risk_flags,
                    "confidence_score": final_confidence,
                }
                review_source_type = "document"
                review_source_id = doc.id

            existing_review = (
                db.query(ReviewItem)
                .filter(
                    ReviewItem.source_type == review_source_type,
                    ReviewItem.source_id == review_source_id,
                    ReviewItem.status == "pending",
                )
                .first()
            )

            if not existing_review:
                review_item = ReviewItem(
                    id=uuid.uuid4(),
                    review_type=review_type,
                    status="pending",
                    priority=priority,
                    source_type=review_source_type,
                    source_id=review_source_id,
                    title=f"Review Needed: {fname}",
                    summary=review_summary,
                    suggested_action=(
                        "Review and correct the extracted data before bookkeeping."
                        if review_type == "extraction"
                        else "Review the AI-generated journal entry account classification."
                    ),
                    original_payload=review_payload,
                )
                db.add(review_item)
            review_item_created = True

            yield f"data: {json.dumps({'stage': 'review_queued', 'percentage': 95, 'message': f'⚠️ Routed to Human Review Queue ({priority} priority). Flags: {flags_str}'})}\n\n"
        else:
            je_ref = str(saved_journal_id)[:8] if saved_journal_id else "JE"
            yield f"data: {json.dumps({'stage': 'journal_created', 'percentage': 95, 'message': f'✓ Balanced journal entry created with #{je_ref}'})}\n\n"

        doc.status = final_status
        db.commit()

        # 4. Audit Trail Event (idempotent)
        existing_audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "extraction_completed",
                AuditEvent.source_id == doc.id,
            )
            .first()
        )
        if not existing_audit:
            log_event(
                db=db,
                event_type="extraction_completed",
                source_type="document",
                source_id=doc.id,
                actor_type="agent",
                actor_name="DocumentProcessingGraph",
                input_snapshot={
                    "document_id": str(doc_uuid),
                    "original_filename": fname,
                },
                output_snapshot={
                    "status": final_status,
                    "confidence_score": final_confidence,
                    "needs_review": needs_review,
                    "extraction_id": str(extraction.id),
                    "journal_entry_id": (
                        str(saved_journal_id) if saved_journal_id else None
                    ),
                    "review_item_created": review_item_created,
                },
                confidence_score=final_confidence,
                rationale=final_rationale,
                document_id=doc.id,
            )
            db.commit()

        yield f"data: {json.dumps({'stage': 'completed', 'percentage': 100, 'status': final_status, 'confidence_score': final_confidence, 'vendor_name': vendor, 'total_amount': tot_amount, 'currency': curr, 'message': f'🎉 Document \"{fname}\" processing completed successfully!'})}\n\n"


    except Exception as e:
        logger.error(
            "Error processing document %s in stream: %s",
            document_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        yield f"data: {json.dumps({'stage': 'error', 'message': f'Document processing failed: {str(e)}'})}\n\n"
    finally:
        db.close()


def process_document_background(
    document_id: str | uuid.UUID,
    stored_file_path: str | None = None,
    mime_type: str | None = None,
    original_filename: str | None = None,
    document_type: str = "unknown",
) -> None:
    """Execute LangGraph document intake & bookkeeping workflow by consuming stream generator."""
    for _ in stream_document_processing(
        document_id, stored_file_path, mime_type, original_filename, document_type
    ):
        pass

