import json
import logging
import uuid
from collections.abc import Generator
from datetime import date, datetime
from typing import Any

from app.agents.orchestrator import document_processing_graph
from app.agents.schemas import BookkeepingOutcome
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.review import ReviewItem
from app.services.audit_service import log_event
from app.services.bookkeeping_persistence import persist_bookkeeping_outcome
from app.services.document_extraction import extract_document_content

logger = logging.getLogger(__name__)


def _sse_event(payload: dict[str, Any]) -> str:
    """Serialize a payload as one Server-Sent Events message."""
    return f"data: {json.dumps(payload, default=str)}\n\n"


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
    """Execute the document workflow and yield real-time SSE events."""
    logger.info(
        "Starting streaming document processing for document ID: %s", document_id
    )
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        if not doc:
            logger.error("Document %s not found in DB.", document_id)
            yield _sse_event(
                {
                    "stage": "error",
                    "message": f"Document [{document_id}] not found.",
                }
            )
            return

        # Guard against duplicate concurrent execution or re-execution.
        if doc.status in (
            "extracted",
            "ready_to_post",
            "review_required",
            "extraction_review_required",
            "bookkeeping_review_required",
        ):
            logger.info(
                "Document %s already processed (status=%s). Returning results.",
                document_id,
                doc.status,
            )
            existing_extraction = (
                db.query(DocumentExtraction)
                .filter(DocumentExtraction.document_id == doc.id)
                .first()
            )
            vendor = (
                existing_extraction.vendor_name if existing_extraction else "Document"
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
            yield _sse_event(
                {
                    "stage": "completed",
                    "percentage": 100,
                    "status": doc.status,
                    "confidence_score": conf,
                    "vendor_name": vendor,
                    "total_amount": tot_amount,
                    "currency": curr,
                    "message": (
                        f'Document "{doc.original_filename}" is already processed.'
                    ),
                }
            )
            return

        file_path = stored_file_path or doc.stored_file_path
        effective_mime = mime_type or doc.mime_type
        fname = original_filename or doc.original_filename

        doc.status = "extracting"
        db.commit()

        yield _sse_event(
            {
                "stage": "init",
                "percentage": 10,
                "message": f'Document Intake pipeline initialized for "{fname}"...',
            }
        )

        # Step 1: Text & OCR Extraction
        yield _sse_event(
            {
                "stage": "ocr_started",
                "percentage": 25,
                "message": (
                    "Extracting text & visual tokens via OCR parser "
                    f"({effective_mime})..."
                ),
            }
        )

        raw_text, image_b64 = extract_document_content(
            file_path=file_path,
            mime_type=effective_mime,
        )

        char_count = len(raw_text) if raw_text else 0
        yield _sse_event(
            {
                "stage": "ocr_extracted",
                "percentage": 40,
                "message": f"Extracted {char_count} characters of content from file.",
                "text_preview": (raw_text[:180] + "...") if raw_text else None,
            }
        )

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

        yield _sse_event(
            {
                "stage": "coa_loaded",
                "percentage": 50,
                "message": (
                    f"Loaded {len(coa_list)} Chart of Accounts entries "
                    "for AI classifier."
                ),
            }
        )

        # Step 3: Stream LangGraph execution.
        yield _sse_event(
            {
                "stage": "intake_agent",
                "percentage": 55,
                "message": (
                    "Invoking Document Intake Agent (Gemini 3 Flash) "
                    "for entity extraction..."
                ),
            }
        )

        initial_state: dict[str, Any] = {
            "document_id": str(doc_uuid),
            "original_filename": fname,
            "mime_type": effective_mime,
            "stored_file_path": file_path,
            "raw_text": raw_text or None,
            "image_base64": image_b64,
            "document_type": document_type,
            "status": "extracting",
            "chart_of_accounts": coa_list,
        }

        final_state: dict[str, Any] = dict(initial_state)

        for step_output in document_processing_graph.stream(initial_state):
            logger.debug(
                "Document processing graph step output: %s", step_output.keys()
            )
            # 1. Document Intake Agent Node
            if "document_intake" in step_output:
                intake_data = step_output["document_intake"]
                final_state.update(intake_data)
                vendor = intake_data.get("vendor_name") or "Unknown Vendor"
                tot_amount = intake_data.get("total_amount")
                curr = intake_data.get("currency", "IDR")
                conf = float(intake_data.get("confidence_score", 0.0))
                needs_rev = intake_data.get("needs_review", False)

                yield _sse_event(
                    {
                        "stage": "intake_done",
                        "percentage": 70,
                        "vendor_name": vendor,
                        "total_amount": tot_amount,
                        "currency": curr,
                        "confidence_score": conf,
                        "message": (
                            f"✓ Document Intake Agent: Extracted {vendor} • "
                            f"{curr} {tot_amount or 0:,.0f} "
                            f"(Confidence: {int(conf * 100)}%)"
                        ),
                    }
                )

                if not needs_rev:
                    yield _sse_event(
                        {
                            "stage": "bookkeeping_agent",
                            "percentage": 75,
                            "message": (
                                "Invoking Bookkeeping Agent (Gemini 3 Flash) "
                                "for Chart of Accounts classification..."
                            ),
                        }
                    )

            # 2. Bookkeeping Agent Node
            if "bookkeeping" in step_output:
                bookkeeping_data = step_output["bookkeeping"]
                final_state.update(bookkeeping_data)
                lines = bookkeeping_data.get("journal_lines") or []
                is_bal = bookkeeping_data.get("is_balanced", True)
                uses_sens = bookkeeping_data.get("uses_sensitive_account", False)

                yield _sse_event(
                    {
                        "stage": "bookkeeping_done",
                        "percentage": 88,
                        "lines_count": len(lines),
                        "message": (
                            f"✓ Bookkeeping Agent: Classified {len(lines)} "
                            f"journal entry lines (Balanced: {is_bal}, "
                            f"Sensitive: {uses_sens})"
                        ),
                    }
                )

            # 3. Review Router Node (if routed)
            if "review_router" in step_output:
                router_data = step_output["review_router"]
                final_state.update(router_data)
                yield _sse_event(
                    {
                        "stage": "review_queued",
                        "percentage": 92,
                        "message": (
                            "⚠️ Low confidence or sensitive account flagged. "
                            "Routing to Human Review Queue."
                        ),
                    }
                )

        vendor = final_state.get("vendor_name") or "Unknown Vendor"
        tot_amount = final_state.get("total_amount")
        curr = final_state.get("currency", "IDR")
        final_confidence = float(final_state.get("confidence_score", 0.0))
        final_status = final_state.get("status", "extracted")
        needs_review = final_state.get("needs_review", False)
        final_risk_flags = final_state.get("risk_flags", []) or []
        final_rationale = final_state.get("rationale")

        provider_meta = {
            "low_confidence_fields": final_state.get("low_confidence_fields", [])
        }

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
            extraction.provider_metadata = provider_meta
            extraction.confidence_score = final_confidence
            extraction.rationale = final_rationale
            extraction.status = "extracted" if not needs_review else "draft"
        else:
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
                provider_metadata=provider_meta,
                confidence_score=final_confidence,
                rationale=final_rationale,
                status="extracted" if not needs_review else "draft",
            )
            db.add(extraction)

        db.flush()
        db.refresh(extraction)

        # 2. Persist bookkeeping through the shared, caller-transactional service.
        proposed_journal = (
            final_state.get("journal_entry")
            or final_state.get("proposed_journal")
            or final_state.get("journal_lines")
        )
        saved_journal_id = None
        save_errors: list[str] = []
        bookkeeping_persistence = None
        bookkeeping_attempted = proposed_journal is not None or final_status in (
            "ready_to_post",
            "bookkeeping_review_required",
        )
        if bookkeeping_attempted:
            bookkeeping_status = (
                final_status
                if final_status
                in {"ready_to_post", "bookkeeping_review_required", "failed"}
                else (
                    "bookkeeping_review_required" if needs_review else "ready_to_post"
                )
            )
            lines = proposed_journal or []
            outcome = BookkeepingOutcome(
                entry_date=final_state.get("entry_date"),
                entry_description=final_state.get("entry_description"),
                journal_lines=lines,
                total_debit=float(
                    final_state.get("total_debit")
                    or sum(float(line.get("debit_amount", 0.0)) for line in lines)
                ),
                total_credit=float(
                    final_state.get("total_credit")
                    or sum(float(line.get("credit_amount", 0.0)) for line in lines)
                ),
                is_balanced=bool(final_state.get("is_balanced", True)),
                uses_sensitive_account=bool(
                    final_state.get("uses_sensitive_account", False)
                ),
                risk_flags=final_risk_flags,
                confidence_score=final_confidence,
                rationale=final_rationale,
                warnings=final_state.get("warnings", []) or [],
                status=bookkeeping_status,
                needs_review=needs_review,
            )
            bookkeeping_persistence = persist_bookkeeping_outcome(
                db=db,
                document=doc,
                extraction=extraction,
                outcome=outcome,
            )
            if bookkeeping_persistence.success:
                saved_journal_id = (
                    str(bookkeeping_persistence.journal_entry_id)
                    if bookkeeping_persistence.journal_entry_id
                    else None
                )
                final_status = bookkeeping_persistence.status
            else:
                save_errors = bookkeeping_persistence.errors
                final_status = "failed"
                needs_review = False

        # 3. Extraction review remains wrapper-specific. Bookkeeping review is
        # created and deduplicated by persist_bookkeeping_outcome().
        review_item_created = bool(
            bookkeeping_persistence and bookkeeping_persistence.review_item_created
        )
        review_item_queued = bool(
            bookkeeping_persistence and bookkeeping_persistence.review_item_id
        )
        flags_str = ", ".join(final_risk_flags) if final_risk_flags else "None"

        if final_status == "extraction_review_required":
            is_balanced = final_state.get("is_balanced", True)
            is_sensitive = "uses_sensitive_account" in final_risk_flags
            priority = "high" if is_sensitive or not is_balanced else "normal"
            review_summary = (
                f"Agent flagged document. Conf: {final_confidence:.2f}, "
                f"Flags: {flags_str}"
            )
            review_payload = {
                "vendor_name": final_state.get("vendor_name"),
                "transaction_date": str(final_state.get("transaction_date") or ""),
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

            existing_review = (
                db.query(ReviewItem)
                .filter(
                    ReviewItem.source_type == "document",
                    ReviewItem.source_id == doc.id,
                    ReviewItem.status == "pending",
                )
                .first()
            )

            if not existing_review:
                review_item = ReviewItem(
                    id=uuid.uuid4(),
                    review_type="extraction",
                    status="pending",
                    priority=priority,
                    source_type="document",
                    source_id=doc.id,
                    title=f"Review Needed: {fname}",
                    summary=review_summary,
                    suggested_action=(
                        "Review and correct the extracted data before bookkeeping."
                    ),
                    original_payload=review_payload,
                )
                db.add(review_item)
                review_item_created = True
            review_item_queued = True

            yield _sse_event(
                {
                    "stage": "review_queued",
                    "percentage": 95,
                    "message": (
                        f"⚠️ Routed to Human Review Queue ({priority} priority). "
                        f"Flags: {flags_str}"
                    ),
                }
            )
        elif review_item_queued:
            priority = (
                "high"
                if (
                    final_state.get("uses_sensitive_account", False)
                    or not final_state.get("is_balanced", True)
                )
                else "normal"
            )
            yield _sse_event(
                {
                    "stage": "review_queued",
                    "percentage": 95,
                    "message": (
                        f"⚠️ Routed to Human Review Queue ({priority} priority). "
                        f"Flags: {flags_str}"
                    ),
                }
            )
        elif saved_journal_id:
            je_ref = str(saved_journal_id)[:8] if saved_journal_id else "JE"
            yield _sse_event(
                {
                    "stage": "journal_created",
                    "percentage": 95,
                    "message": f"✓ Balanced journal entry created with #{je_ref}",
                }
            )

        doc.status = final_status
        extracted_document_type = final_state.get("document_type")
        if extracted_document_type in ("invoice", "receipt"):
            doc.document_type = extracted_document_type

        # 4. Audit Trail Event: extraction_completed (idempotent)
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
                actor_name="IntakeAgent",
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
                    "low_confidence_fields": final_state.get(
                        "low_confidence_fields", []
                    ),
                },
                confidence_score=final_confidence,
                rationale=final_rationale,
                document_id=doc.id,
            )

        # 5. Audit Trail Event: bookkeeping_completed (if bookkeeping was executed)
        if bookkeeping_attempted:
            if saved_journal_id:
                je_uuid = (
                    uuid.UUID(saved_journal_id)
                    if isinstance(saved_journal_id, str)
                    else saved_journal_id
                )
                existing_bk_audit = (
                    db.query(AuditEvent)
                    .filter(
                        AuditEvent.event_type == "bookkeeping_completed",
                        AuditEvent.source_id == je_uuid,
                    )
                    .first()
                )
                if not existing_bk_audit:
                    log_event(
                        db=db,
                        event_type="bookkeeping_completed",
                        source_type="journal_entry",
                        source_id=je_uuid,
                        actor_type="agent",
                        actor_name="BookkeepingAgent",
                        input_snapshot={
                            "document_id": str(doc.id),
                            "extraction_id": str(extraction.id),
                        },
                        output_snapshot={
                            "decision": bookkeeping_persistence.decision,
                            "reasoning": bookkeeping_persistence.reasoning,
                            "journal_entry_id": str(saved_journal_id),
                            "status": "review_required" if needs_review else "draft",
                            "is_balanced": final_state.get("is_balanced", True),
                        },
                        confidence_score=final_confidence,
                        rationale=final_rationale,
                        document_id=doc.id,
                    )
            else:
                # Failure case: bookkeeping ran but saving failed.
                existing_bk_fail_audit = (
                    db.query(AuditEvent)
                    .filter(
                        AuditEvent.event_type == "bookkeeping_completed",
                        AuditEvent.source_id == doc.id,
                    )
                    .first()
                )
                if not existing_bk_fail_audit:
                    fail_reasoning = list(save_errors) if save_errors else []
                    if not fail_reasoning:
                        if final_state.get("error"):
                            fail_reasoning.append(str(final_state["error"]))
                        elif not final_state.get("is_balanced", True):
                            fail_reasoning.append(
                                "Journal entry double-entry balance validation failed."
                            )
                        else:
                            fail_reasoning.append(
                                "Bookkeeping agent failed to produce a valid "
                                "journal entry."
                            )

                    log_event(
                        db=db,
                        event_type="bookkeeping_completed",
                        source_type="document",
                        source_id=doc.id,
                        actor_type="agent",
                        actor_name="BookkeepingAgent",
                        input_snapshot={
                            "document_id": str(doc.id),
                            "extraction_id": str(extraction.id),
                        },
                        output_snapshot={
                            "decision": "failed",
                            "reasoning": fail_reasoning,
                            "status": "failed",
                            "journal_entry_id": None,
                        },
                        confidence_score=final_confidence,
                        rationale=final_rationale
                        or "Bookkeeping classification failed validation.",
                        document_id=doc.id,
                    )

        # The extraction, journal, review item, document status, and wrapper-specific
        # audit events become durable together.
        db.commit()

        yield _sse_event(
            {
                "stage": "completed",
                "percentage": 100,
                "status": final_status,
                "confidence_score": final_confidence,
                "vendor_name": vendor,
                "total_amount": tot_amount,
                "currency": curr,
                "message": f'🎉 Document "{fname}" processing completed successfully!',
            }
        )

    except Exception as e:
        logger.error(
            "Error processing document %s in stream: %s",
            document_id,
            str(e),
            exc_info=True,
        )
        db.rollback()
        yield _sse_event(
            {
                "stage": "error",
                "message": "Document processing failed. Please check the server logs.",
            }
        )
    finally:
        db.close()


def process_document_background(
    document_id: str | uuid.UUID,
    stored_file_path: str | None = None,
    mime_type: str | None = None,
    original_filename: str | None = None,
    document_type: str = "unknown",
) -> None:
    """Execute the document workflow by consuming its stream generator."""
    for _ in stream_document_processing(
        document_id, stored_file_path, mime_type, original_filename, document_type
    ):
        pass
