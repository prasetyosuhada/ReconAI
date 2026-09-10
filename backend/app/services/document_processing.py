import logging
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime
from math import isfinite
from time import perf_counter
from typing import Any

from app.agents.orchestrator import document_processing_graph
from app.agents.schemas import BookkeepingOutcome
from app.db.session import SessionLocal
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.review import ReviewItem
from app.schemas.document_content import DocumentContent
from app.services.audit_service import log_event
from app.services.bookkeeping_persistence import persist_bookkeeping_outcome
from app.services.document_extraction import extract_document_content
from app.services.document_progress import publish_document_progress

logger = logging.getLogger(__name__)


def _sse_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one transport-neutral document-processing progress event."""
    return payload


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


def _optional_duration_ms(value: Any) -> float | None:
    """Normalize an optional monotonic duration for audit serialization."""
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(duration) or duration < 0:
        return None
    return round(duration, 2)


def _build_extraction_provider_metadata(
    *,
    document_content: DocumentContent,
    content_extraction_duration_ms: float | None,
    intake_processing_duration_ms: float | None,
    llm_provider: str | None,
    llm_model: str | None,
    workflow_warnings: list[str],
    low_confidence_fields: list[str],
    risk_flags: list[str],
) -> dict[str, Any]:
    """Build the persisted and audited metadata for document extraction."""
    metadata = dict(document_content.provider_metadata)
    warnings = list(dict.fromkeys([*document_content.warnings, *workflow_warnings]))
    durations = {
        "content_extraction": content_extraction_duration_ms,
        "document_intake": intake_processing_duration_ms,
    }
    measured_durations = [
        duration for duration in durations.values() if duration is not None
    ]
    durations["total"] = (
        round(sum(measured_durations), 2) if measured_durations else None
    )
    visual_pages = document_content.visual_pages

    metadata.update(
        {
            "extraction_method": document_content.extraction_method.value,
            "vision_processed_page_numbers": [
                page.page_number for page in visual_pages
            ],
            "vision_page_mime_types": {
                str(page.page_number): page.mime_type for page in visual_pages
            },
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "durations_ms": durations,
            "warnings": warnings,
            "low_confidence_fields": low_confidence_fields,
            "risk_flags": risk_flags,
        }
    )
    return metadata


def stream_document_processing(
    document_id: str | uuid.UUID,
    stored_file_path: str | None = None,
    mime_type: str | None = None,
    original_filename: str | None = None,
    document_type: str = "unknown",
) -> Generator[dict[str, Any], None, None]:
    """Execute the document workflow and yield transport-neutral progress events."""
    logger.info(
        "Starting streaming document processing for document ID: %s", document_id
    )
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    db = SessionLocal()
    try:
        claimed = (
            db.query(Document)
            .filter(Document.id == doc_uuid, Document.status == "uploaded")
            .update({Document.status: "extracting"}, synchronize_session=False)
        )
        if claimed != 1:
            db.rollback()
            existing_doc = db.query(Document).filter(Document.id == doc_uuid).first()
            if existing_doc is not None:
                logger.info(
                    "Document %s was not claimed (status=%s); skipping duplicate run.",
                    document_id,
                    existing_doc.status,
                )
                return
            logger.error("Document %s not found in DB.", document_id)
            yield _sse_event(
                {
                    "stage": "error",
                    "message": f"Document [{document_id}] not found.",
                }
            )
            return
        db.commit()
        doc = db.query(Document).filter(Document.id == doc_uuid).one()

        file_path = stored_file_path or doc.stored_file_path
        effective_mime = mime_type or doc.mime_type
        fname = original_filename or doc.original_filename

        yield _sse_event(
            {
                "stage": "init",
                "percentage": 10,
                "message": f'Document Intake pipeline initialized for "{fname}"...',
            }
        )

        # Step 1: Provider-neutral text and visual content extraction
        yield _sse_event(
            {
                "stage": "content_extraction_started",
                "percentage": 25,
                "message": (
                    "Inspecting embedded text and visual document pages "
                    f"({effective_mime})..."
                ),
            }
        )

        content_started_at = perf_counter()
        document_content = extract_document_content(
            file_path=file_path,
            mime_type=effective_mime,
        )
        content_extraction_duration_ms = _optional_duration_ms(
            (perf_counter() - content_started_at) * 1000
        )
        raw_text = document_content.text
        visual_page_count = len(document_content.visual_pages)

        char_count = len(raw_text) if raw_text else 0
        yield _sse_event(
            {
                "stage": "content_extracted",
                "percentage": 40,
                "message": (
                    f"Prepared {char_count} text characters and "
                    f"{visual_page_count} visual page(s)."
                ),
                "text_preview": (raw_text[:180] + "...") if raw_text else None,
                "extraction_method": document_content.extraction_method.value,
                "visual_page_count": visual_page_count,
                "warnings": document_content.warnings,
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
                    "Invoking Document Intake Agent with the configured LLM "
                    "for entity extraction..."
                ),
            }
        )

        initial_state: dict[str, Any] = {
            "document_id": str(doc_uuid),
            "original_filename": fname,
            "mime_type": effective_mime,
            "stored_file_path": file_path,
            "document_content": document_content,
            "raw_text": raw_text or None,
            "document_type": document_type,
            "status": "extracting",
            "chart_of_accounts": coa_list,
        }

        final_state: dict[str, Any] = dict(initial_state)
        intake_confidence = 0.0
        intake_rationale: str | None = None
        intake_status = "failed"
        intake_needs_review = False
        intake_processing_duration_ms: float | None = None
        intake_llm_provider: str | None = None
        intake_llm_model: str | None = None
        intake_warnings: list[str] = []
        intake_low_confidence_fields: list[str] = []
        intake_risk_flags: list[str] = []
        bookkeeping_confidence = 0.0
        bookkeeping_rationale: str | None = None
        bookkeeping_status: str | None = None
        bookkeeping_needs_review = False
        bookkeeping_processing_duration_ms: float | None = None
        bookkeeping_completed_at: datetime | None = None
        bookkeeping_seen = False

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
                intake_confidence = float(
                    intake_data.get(
                        "intake_confidence_score",
                        intake_data.get("confidence_score", 0.0),
                    )
                )
                intake_rationale = intake_data.get(
                    "intake_rationale", intake_data.get("rationale")
                )
                intake_status = intake_data.get(
                    "intake_status", intake_data.get("status", "failed")
                )
                intake_needs_review = bool(
                    intake_data.get(
                        "intake_needs_review",
                        intake_data.get("needs_review", False),
                    )
                )
                intake_processing_duration_ms = _optional_duration_ms(
                    intake_data.get("intake_processing_duration_ms")
                )
                intake_llm_provider = intake_data.get("intake_llm_provider")
                intake_llm_model = intake_data.get("intake_llm_model")
                intake_warnings = list(intake_data.get("warnings", []) or [])
                intake_low_confidence_fields = list(
                    intake_data.get("low_confidence_fields", []) or []
                )
                intake_risk_flags = list(intake_data.get("risk_flags", []) or [])

                yield _sse_event(
                    {
                        "stage": "intake_done",
                        "percentage": 70,
                        "vendor_name": vendor,
                        "total_amount": tot_amount,
                        "currency": curr,
                        "confidence_score": intake_confidence,
                        "message": (
                            f"✓ Document Intake Agent: Extracted {vendor} • "
                            f"{curr} {tot_amount or 0:,.0f} "
                            f"(Confidence: {int(intake_confidence * 100)}%)"
                        ),
                    }
                )

                if not intake_needs_review:
                    yield _sse_event(
                        {
                            "stage": "bookkeeping_agent",
                            "percentage": 75,
                            "message": (
                                "Invoking Bookkeeping Agent with the configured LLM "
                                "for Chart of Accounts classification..."
                            ),
                        }
                    )

            # 2. Bookkeeping Agent Node
            if "bookkeeping" in step_output:
                bookkeeping_data = step_output["bookkeeping"]
                bookkeeping_completed_at = datetime.now(UTC)
                final_state.update(bookkeeping_data)
                bookkeeping_seen = True
                bookkeeping_confidence = float(
                    bookkeeping_data.get(
                        "bookkeeping_confidence_score",
                        bookkeeping_data.get("confidence_score", 0.0),
                    )
                )
                bookkeeping_rationale = bookkeeping_data.get(
                    "bookkeeping_rationale", bookkeeping_data.get("rationale")
                )
                bookkeeping_status = bookkeeping_data.get(
                    "bookkeeping_status", bookkeeping_data.get("status")
                )
                bookkeeping_needs_review = bool(
                    bookkeeping_data.get(
                        "bookkeeping_needs_review",
                        bookkeeping_data.get("needs_review", False),
                    )
                )
                bookkeeping_processing_duration_ms = _optional_duration_ms(
                    bookkeeping_data.get("bookkeeping_processing_duration_ms")
                )
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
        final_status = final_state.get("status", "extracted")
        final_risk_flags = final_state.get("risk_flags", []) or []
        terminal_confidence = (
            bookkeeping_confidence if bookkeeping_seen else intake_confidence
        )

        provider_meta = _build_extraction_provider_metadata(
            document_content=document_content,
            content_extraction_duration_ms=content_extraction_duration_ms,
            intake_processing_duration_ms=intake_processing_duration_ms,
            llm_provider=intake_llm_provider,
            llm_model=intake_llm_model,
            workflow_warnings=intake_warnings,
            low_confidence_fields=intake_low_confidence_fields,
            risk_flags=intake_risk_flags,
        )

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
            extraction.confidence_score = intake_confidence
            extraction.rationale = intake_rationale
            extraction.status = "extracted" if intake_status == "extracted" else "draft"
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
                confidence_score=intake_confidence,
                rationale=intake_rationale,
                status="extracted" if intake_status == "extracted" else "draft",
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
        bookkeeping_attempted = bookkeeping_seen
        if bookkeeping_attempted:
            outcome_status = (
                bookkeeping_status
                if bookkeeping_status
                in {"ready_to_post", "bookkeeping_review_required", "failed"}
                else (
                    "bookkeeping_review_required"
                    if bookkeeping_needs_review
                    else "ready_to_post"
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
                confidence_score=bookkeeping_confidence,
                rationale=bookkeeping_rationale,
                warnings=final_state.get("warnings", []) or [],
                status=outcome_status,
                needs_review=bookkeeping_needs_review,
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

        # 3. Extraction review remains wrapper-specific. Bookkeeping review is
        # created and deduplicated by persist_bookkeeping_outcome().
        extraction_review_item_created = False
        review_item_queued = bool(
            bookkeeping_persistence and bookkeeping_persistence.review_item_id
        )
        flags_str = ", ".join(final_risk_flags) if final_risk_flags else "None"

        if intake_status == "extraction_review_required":
            is_balanced = final_state.get("is_balanced", True)
            is_sensitive = "uses_sensitive_account" in final_risk_flags
            priority = "high" if is_sensitive or not is_balanced else "normal"
            review_summary = (
                f"Agent flagged document. Conf: {intake_confidence:.2f}, "
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
                "rationale": intake_rationale,
                "risk_flags": final_risk_flags,
                "confidence_score": intake_confidence,
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
                extraction_review_item_created = True
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
                    "status": intake_status,
                    "confidence_score": intake_confidence,
                    "needs_review": intake_needs_review,
                    "extraction_id": str(extraction.id),
                    "journal_entry_id": (
                        str(saved_journal_id) if saved_journal_id else None
                    ),
                    "review_item_created": extraction_review_item_created,
                    "processing_duration_ms": intake_processing_duration_ms,
                    "low_confidence_fields": provider_meta["low_confidence_fields"],
                    "warnings": provider_meta["warnings"],
                    "risk_flags": provider_meta["risk_flags"],
                    "provider_metadata": provider_meta,
                },
                confidence_score=intake_confidence,
                rationale=intake_rationale,
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
                            "status": final_status,
                            "journal_status": (
                                "review_required"
                                if bookkeeping_needs_review
                                else "draft"
                            ),
                            "needs_review": bookkeeping_needs_review,
                            "processing_duration_ms": (
                                bookkeeping_processing_duration_ms
                            ),
                            "is_balanced": final_state.get("is_balanced", True),
                        },
                        confidence_score=bookkeeping_confidence,
                        rationale=bookkeeping_rationale,
                        document_id=doc.id,
                        created_at=bookkeeping_completed_at,
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
                            "processing_duration_ms": (
                                bookkeeping_processing_duration_ms
                            ),
                        },
                        confidence_score=bookkeeping_confidence,
                        rationale=bookkeeping_rationale
                        or "Bookkeeping classification failed validation.",
                        document_id=doc.id,
                        created_at=bookkeeping_completed_at,
                    )

        # The extraction, journal, review item, document status, and wrapper-specific
        # audit events become durable together.
        db.commit()

        yield _sse_event(
            {
                "stage": "completed",
                "percentage": 100,
                "status": final_status,
                "confidence_score": terminal_confidence,
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
    """Execute the document workflow and publish progress to Redis Streams."""
    for event in stream_document_processing(
        document_id, stored_file_path, mime_type, original_filename, document_type
    ):
        publish_document_progress(document_id, event)
