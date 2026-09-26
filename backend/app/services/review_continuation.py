"""Atomic extraction decisions with classification outside the write transaction."""

import logging
import uuid
from copy import deepcopy
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.bookkeeping import classify_bookkeeping
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.audit_service import log_event
from app.services.bookkeeping_persistence import (
    load_active_chart_of_accounts,
    persist_bookkeeping_outcome,
)
from app.services.review_validation import (
    ExtractionCorrectionError,
    allowlisted_correction,
    validate_review_extraction,
)

logger = logging.getLogger(__name__)


class ReviewContinuationError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        review_status: str | None = None,
        next_workflow_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.review_status = review_status
        self.next_workflow_status = next_workflow_status


class ExtractionReviewResolution(BaseModel):
    id: uuid.UUID
    status: Literal["approved", "edited", "rejected"]
    resolved_at: datetime
    next_workflow_status: str


class SourceSnapshot(BaseModel):
    document_id: uuid.UUID
    extraction_id: uuid.UUID | None
    document_status: str
    payload: dict[str, Any]


def _pending_review(db: Session, review_id: uuid.UUID, *, lock: bool) -> ReviewItem:
    query = db.query(ReviewItem).filter(ReviewItem.id == review_id).populate_existing()
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise ReviewContinuationError(404, "review_not_found", "Review item not found.")
    if item.source_type != "document" or item.review_type != "extraction":
        raise ReviewContinuationError(
            409, "invalid_review_type", "An extraction review is required."
        )
    if item.status != "pending":
        doc = (
            db.query(Document)
            .filter(Document.id == item.source_id)
            .populate_existing()
            .first()
        )
        raise ReviewContinuationError(
            409,
            "review_already_resolved",
            "This review has already been resolved. Refresh the review queue.",
            review_status=item.status,
            next_workflow_status=doc.status if doc else None,
        )
    return item


def _source_snapshot(
    db: Session,
    item: ReviewItem,
    *,
    lock: bool,
) -> tuple[SourceSnapshot, Document, DocumentExtraction | None]:
    query = db.query(Document).filter(Document.id == item.source_id).populate_existing()
    doc = (query.with_for_update() if lock else query).first()
    if doc is None:
        raise ReviewContinuationError(
            404, "document_not_found", "Source document not found."
        )
    query = (
        db.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc.id)
        .order_by(DocumentExtraction.created_at.desc(), DocumentExtraction.id.desc())
        .populate_existing()
    )
    extraction = (query.with_for_update() if lock else query).first()
    payload = (
        deepcopy(item.original_payload)
        if isinstance(item.original_payload, dict)
        else {}
    )
    payload["document_type"] = doc.document_type
    if extraction:
        for field in ("vendor_name", "currency", "line_items", "raw_text", "rationale"):
            payload[field] = deepcopy(getattr(extraction, field))
        for field in (
            "subtotal_amount",
            "tax_amount",
            "total_amount",
            "confidence_score",
        ):
            value = getattr(extraction, field)
            payload[field] = float(value) if value is not None else None
        payload["transaction_date"] = (
            extraction.transaction_date.isoformat()
            if extraction.transaction_date
            else None
        )
        if isinstance(payload["line_items"], dict):
            wrapped = payload["line_items"]
            if "items" in wrapped:
                payload["line_items"] = wrapped["items"]
            elif "line_items" in wrapped:
                payload["line_items"] = wrapped["line_items"]
        if payload["line_items"] is None:
            payload["line_items"] = []
    return (
        SourceSnapshot(
            document_id=doc.id,
            extraction_id=extraction.id if extraction else None,
            document_status=doc.status,
            payload=payload,
        ),
        doc,
        extraction,
    )


def _persist_extraction(
    db: Session,
    doc: Document,
    extraction: DocumentExtraction | None,
    payload: dict[str, Any],
) -> DocumentExtraction:
    if extraction is None:
        extraction = DocumentExtraction(
            id=uuid.uuid4(),
            document_id=doc.id,
            raw_text=payload.get("raw_text"),
            confidence_score=payload.get("confidence_score") or 0.0,
            rationale=payload.get("rationale"),
        )
        db.add(extraction)
    doc.document_type = payload["document_type"]
    for field in (
        "vendor_name",
        "currency",
        "subtotal_amount",
        "tax_amount",
        "total_amount",
        "line_items",
    ):
        setattr(extraction, field, payload[field])
    extraction.transaction_date = date.fromisoformat(payload["transaction_date"])
    extraction.status = "extracted"
    db.flush()
    return extraction


def resolve_extraction_review(
    *,
    db: Session,
    review_id: uuid.UUID,
    decision: Literal["approved", "edited"],
    edited_payload: dict[str, Any] | None = None,
    resolution_note: str | None = None,
) -> ExtractionReviewResolution:
    """Own one request's session; commit all decision effects once, or roll back.

    Concurrent callers may classify independently. Only the pending-state winner may
    persist. No connection or row lock is held during the external model call.
    """
    correction = (
        allowlisted_correction(edited_payload or {}) if decision == "edited" else {}
    )
    try:
        item = _pending_review(db, review_id, lock=False)
        snapshot, _, _ = _source_snapshot(db, item, lock=False)
        payload = validate_review_extraction({**snapshot.payload, **correction})
        coa = load_active_chart_of_accounts(db)
        # End the read transaction and return its connection before external I/O.
        db.rollback()
        resolved_at = datetime.now(UTC)
        started_at = perf_counter()
        try:
            outcome = classify_bookkeeping(
                extraction_data={
                    **allowlisted_correction(payload),
                    "extraction_notes": payload.get("extraction_notes"),
                },
                chart_of_accounts=coa,
            )
        except Exception:
            logger.exception(
                "Bookkeeping classification failed for review %s", review_id
            )
            outcome = None
        duration_ms = round(max(0.0, (perf_counter() - started_at) * 1000), 2)
        completed_at = datetime.now(UTC)
        # Lock/reload in a fixed order for approve, edit, and reject alike.
        item = _pending_review(db, review_id, lock=True)
        if outcome is None or outcome.status == "failed" or not outcome.journal_lines:
            raise ReviewContinuationError(
                503,
                "review_continuation_failed",
                "Bookkeeping could not complete. "
                "Your review is still pending; please retry.",
            )

        current, doc, extraction = _source_snapshot(db, item, lock=True)
        if current != snapshot:
            raise ReviewContinuationError(
                409,
                "review_source_changed",
                "The extraction changed during review. Refresh it before continuing.",
                review_status=item.status,
                next_workflow_status=doc.status,
            )
        extraction = _persist_extraction(db, doc, extraction, payload)
        persistence = persist_bookkeeping_outcome(
            db=db, document=doc, extraction=extraction, outcome=outcome
        )
        if not persistence.success:
            raise ReviewContinuationError(
                503,
                "review_continuation_failed",
                "The bookkeeping result could not be saved. "
                "Your review is still pending; please retry.",
            )
        item.status = decision
        item.edited_payload = correction if decision == "edited" else None
        item.resolution_note = resolution_note
        item.resolved_by = "human_user"
        item.resolved_at = resolved_at
        log_event(
            db=db,
            event_type=f"review_item_{decision}",
            source_type="review_item",
            source_id=item.id,
            actor_type="human",
            actor_name="human_user",
            human_action=decision,
            input_snapshot={
                "resolution_note": resolution_note,
                "review_type": "extraction",
                "original_extraction_id": str(snapshot.extraction_id)
                if snapshot.extraction_id
                else None,
                "original_fields": allowlisted_correction(snapshot.payload),
                "edited_payload": correction,
            },
            output_snapshot={
                "status": decision,
                "next_workflow_status": persistence.status,
                "extraction_id": str(extraction.id),
                "effective_fields": allowlisted_correction(payload),
                "journal_entry_id": str(persistence.journal_entry_id),
                "downstream_review_item_id": str(persistence.review_item_id)
                if persistence.review_item_id
                else None,
            },
            document_id=doc.id,
            created_at=resolved_at,
        )
        log_event(
            db=db,
            event_type="bookkeeping_completed",
            source_type="journal_entry",
            source_id=persistence.journal_entry_id,
            actor_type="agent",
            actor_name="BookkeepingAgent",
            input_snapshot={
                "review_item_id": str(item.id),
                "extraction_id": str(extraction.id),
                "review_type": "extraction",
                "triggered_by": "extraction_review_approval",
            },
            output_snapshot={
                "decision": persistence.decision,
                "reasoning": persistence.reasoning,
                "status": persistence.status,
                "journal_entry_id": str(persistence.journal_entry_id),
                "needs_review": outcome.needs_review,
                "processing_duration_ms": duration_ms,
            },
            confidence_score=outcome.confidence_score,
            rationale=outcome.rationale,
            document_id=doc.id,
            created_at=completed_at,
        )
        result = ExtractionReviewResolution(
            id=item.id,
            status=decision,
            resolved_at=resolved_at,
            next_workflow_status=persistence.status,
        )
        db.commit()
        return result
    except (ReviewContinuationError, ExtractionCorrectionError):
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Extraction review continuation failed for %s", review_id)
        raise ReviewContinuationError(
            503,
            "review_continuation_failed",
            "The review could not be completed. "
            "Please retry; no partial decision was saved.",
        ) from exc


def reject_extraction_review(
    *,
    db: Session,
    review_id: uuid.UUID,
    resolution_note: str | None = None,
) -> ExtractionReviewResolution:
    """Compete for the same review lock as an in-flight approval or correction."""
    try:
        item = _pending_review(db, review_id, lock=True)
        _, doc, _ = _source_snapshot(db, item, lock=True)
        resolved_at = datetime.now(UTC)
        item.status = "rejected"
        item.resolution_note = resolution_note
        item.resolved_by = "human_user"
        item.resolved_at = resolved_at
        doc.status = "rejected"
        for journal in (
            db.query(JournalEntry).filter(JournalEntry.document_id == doc.id).all()
        ):
            journal.status = "rejected"
        log_event(
            db=db,
            event_type="review_item_rejected",
            source_type="review_item",
            source_id=item.id,
            actor_type="human",
            actor_name="human_user",
            human_action="rejected",
            input_snapshot={
                "resolution_note": resolution_note,
                "review_type": "extraction",
            },
            output_snapshot={"status": "rejected", "next_workflow_status": "rejected"},
            document_id=doc.id,
            created_at=resolved_at,
        )
        result = ExtractionReviewResolution(
            id=item.id,
            status="rejected",
            resolved_at=resolved_at,
            next_workflow_status="rejected",
        )
        db.commit()
        return result
    except ReviewContinuationError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Extraction review rejection failed for %s", review_id)
        raise ReviewContinuationError(
            503,
            "review_continuation_failed",
            "The rejection could not be saved. Please retry.",
        ) from exc
