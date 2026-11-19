"""Atomic direct and human-reviewed journal posting."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.schemas.ledger import PostJournalEntryResponse
from app.schemas.review import (
    ReviewApproveResponse,
    ReviewEditResponse,
    ReviewRejectResponse,
)
from app.services.accounting import (
    CONFIDENCE_THRESHOLD_BOOKKEEPING,
    check_sensitive_accounts,
    post_journal_entry_to_ledger,
)
from app.services.audit_service import log_event
from app.services.journal_edits import ReviewedLine, apply_journal_edits

logger = logging.getLogger(__name__)


class JournalPostingError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        journal_status: str | None = None,
        review_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.journal_status = journal_status
        self.review_status = review_status


def _review_required(
    entry: JournalEntry, review: ReviewItem | None = None
) -> JournalPostingError:
    return JournalPostingError(
        409,
        "posting_review_required",
        "Refresh the journal and check its required approvals in Human Review.",
        entry.status,
        review.status if review else None,
    )


def _not_postable(
    entry: JournalEntry, review: ReviewItem | None = None
) -> JournalPostingError:
    return JournalPostingError(
        409,
        "journal_not_postable",
        "Refresh the journal and inspect its workflow state and review links.",
        entry.status,
        review.status if review else None,
    )


def _journal_for_review(
    db: Session,
    review: ReviewItem,
    candidate: JournalEntry | None = None,
) -> JournalEntry:
    """Resolve either review link. A document may have several journals."""
    conflict = JournalPostingError(
        409,
        "journal_not_postable",
        "Refresh the review and verify its journal link.",
        candidate.status if candidate is not None else None,
        review.status,
    )
    if review.review_type != "bookkeeping":
        raise conflict

    target = review.source_id if review.source_type == "journal_entry" else None
    for payload in (review.original_payload, review.edited_payload):
        if isinstance(payload, dict) and "journal_entry_id" in payload:
            try:
                declared = UUID(str(payload["journal_entry_id"]))
            except ValueError:
                raise conflict from None
            if target is not None and declared != target:
                raise conflict
            target = declared

    if review.source_type not in {"journal_entry", "document"}:
        raise conflict
    if target is None:
        entries = (
            db.query(JournalEntry)
            .filter_by(document_id=review.source_id)
            .limit(2)
            .all()
        )
        if len(entries) > 1:
            raise conflict
        entry = next(iter(entries), None)
    else:
        entry = db.get(JournalEntry, target)
    if entry is None:
        if candidate is not None:
            raise conflict
        raise JournalPostingError(
            404, "not_found", "The journal linked to this review was not found."
        )
    if review.source_type == "document" and entry.document_id != review.source_id:
        raise conflict
    return entry


def _review_matches_lines(review: ReviewItem, lines: list[ReviewedLine]) -> bool:
    payload = (
        review.edited_payload if review.status == "edited" else review.original_payload
    )
    if not isinstance(payload, dict):
        return False
    snapshot = payload.get("lines", payload.get("journal_lines"))
    if not isinstance(snapshot, list):
        return False
    try:
        return [ReviewedLine.model_validate(line) for line in snapshot] == lines
    except ValidationError:
        return False


def _check_state(
    entry: JournalEntry, decision: ReviewItem | None, *, rejecting: bool = False
) -> None:
    if entry.status == "posted":
        raise JournalPostingError(
            409,
            "journal_already_posted",
            "This journal is already posted. Refresh the journal.",
            entry.status,
            decision.status if decision else None,
        )
    if decision is None and entry.status == "review_required":
        raise _review_required(entry)
    allowed = {"draft", "review_required"} if decision else {"draft", "approved"}
    if rejecting:
        # A pending review can still veto an approved but unposted journal.
        allowed.add("approved")
    if entry.status not in allowed or entry.source_type not in {
        "document",
        "manual",
        "import",
        "system",
    }:
        raise _not_postable(entry, decision)


def _lock_posting_rows(
    db: Session,
    journal_id: UUID,
) -> tuple[JournalEntry, list[ReviewItem]]:
    """Acquire document, journal, then Bookkeeping review locks in the common order."""
    missing = JournalPostingError(404, "not_found", "Journal entry not found.")
    candidate = (
        db.query(JournalEntry.document_id).filter_by(id=journal_id).one_or_none()
    )
    if candidate is None:
        raise missing
    document_id = candidate.document_id
    if document_id is not None:
        document = db.get(
            Document, document_id, populate_existing=True, with_for_update=True
        )
        if document is None:
            raise JournalPostingError(404, "not_found", "Linked document not found.")

    entry = db.get(
        JournalEntry, journal_id, populate_existing=True, with_for_update=True
    )
    if entry is None:
        raise missing
    if entry.document_id != document_id:
        raise _not_postable(entry)

    source = and_(
        ReviewItem.source_type == "journal_entry", ReviewItem.source_id == journal_id
    )
    if document_id is not None:
        source = or_(
            source,
            and_(
                ReviewItem.source_type == "document",
                ReviewItem.source_id == document_id,
            ),
        )
    reviews = (
        db.query(ReviewItem)
        .filter(ReviewItem.review_type == "bookkeeping", source)
        .order_by(ReviewItem.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    return entry, reviews


def _require_pending(review: ReviewItem, entry: JournalEntry | None = None) -> None:
    if review.status != "pending":
        raise JournalPostingError(
            409,
            "review_already_resolved",
            "This review has already been resolved. Refresh the review.",
            entry.status if entry else None,
            review.status,
        )


def _lock_review_target(
    db: Session, review: ReviewItem
) -> tuple[JournalEntry, list[ReviewItem]]:
    _require_pending(review)
    candidate = _journal_for_review(db, review)
    entry, reviews = _lock_posting_rows(db, candidate.id)
    # The router loaded the decision before waiting. The locking query refreshed
    # that same session object only if it still belongs to the locked sources.
    if review not in reviews:
        raise _not_postable(entry, review)
    _require_pending(review, entry)
    if _journal_for_review(db, review, candidate=entry).id != entry.id:
        raise _not_postable(entry, review)
    return entry, reviews


def _check_approvals(
    db: Session,
    entry: JournalEntry,
    reviews: list[ReviewItem],
    decision: ReviewItem | None = None,
    *,
    replaced_lines: bool = False,
) -> None:
    if entry.document_id is not None:
        document = entry.document
        if document is None:
            raise JournalPostingError(404, "not_found", "Linked document not found.")
        document_source = and_(
            ReviewItem.source_type == "document", ReviewItem.source_id == document.id
        )
        pending = (
            db.query(ReviewItem)
            .filter(
                document_source,
                ReviewItem.review_type == "extraction",
                ReviewItem.status == "pending",
            )
            .first()
        )
        if pending is not None:
            raise _review_required(entry, pending)
        allowed = {"ready_to_post"}
        if decision is not None:
            allowed.update({"bookkeeping_review_required", "approved"})
            # Older document-linked reviews can predate the Bookkeeping workflow status.
            if decision.source_type == "document":
                allowed.add("uploaded")
        elif entry.status == "approved":
            allowed.add("approved")
        if document.status not in allowed:
            if document.status in {
                "extraction_review_required",
                "bookkeeping_review_required",
            }:
                raise _review_required(entry)
            raise _not_postable(entry, decision)
    elif (
        decision is None and entry.status == "draft" and entry.source_type == "document"
    ):
        raise _not_postable(entry)

    effective_lines = []
    for line in entry.lines:
        if line.account is None or not line.account.is_active:
            raise JournalPostingError(
                422,
                "journal_validation_failed",
                f"Line {line.line_number} requires an active account.",
            )
        effective_lines.append(
            ReviewedLine(
                account_code=line.account.account_code,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                description=line.description,
            )
        )

    approved = False
    for review in reviews:
        if _journal_for_review(db, review, candidate=entry).id != entry.id:
            continue
        if decision is not None and review.id == decision.id:
            # An approve-as-is uses the displayed snapshot when one was recorded.
            original = review.original_payload
            if (
                not replaced_lines
                and isinstance(original, dict)
                and ("lines" in original or "journal_lines" in original)
                and not _review_matches_lines(review, effective_lines)
            ):
                raise _not_postable(entry, review)
            approved = True
            continue
        if review.status not in {"approved", "edited"} or not _review_matches_lines(
            review, effective_lines
        ):
            raise _review_required(entry, review)
        approved = True

    sensitive = check_sensitive_accounts(
        effective_lines, [line.account for line in entry.lines]
    ).requires_human_review
    low_confidence = (
        entry.confidence_score is not None
        and float(entry.confidence_score) < CONFIDENCE_THRESHOLD_BOOKKEEPING
    )
    if (entry.risk_flags or sensitive or low_confidence) and not approved:
        raise _review_required(entry)


@contextmanager
def _posting_transaction(db: Session) -> Iterator[None]:
    try:
        yield
        db.commit()
    except JournalPostingError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Journal posting transaction failed")
        raise JournalPostingError(
            503,
            "posting_failed",
            "Posting could not be confirmed. Refresh the journal before retrying.",
        ) from exc


def _stage_post(db: Session, entry: JournalEntry, actor: str) -> None:
    posted = post_journal_entry_to_ledger(entry, db, posted_by=actor)
    if not posted.success:
        raise JournalPostingError(
            422, "journal_validation_failed", " ".join(posted.errors)
        )
    if entry.document is not None:
        entry.document.status = "posted"


def _audit_post(
    db: Session, entry: JournalEntry, actor: str, review: ReviewItem | None = None
) -> None:
    refs = {"journal_entry_id": str(entry.id)}
    if review is not None:
        refs["review_item_id"] = str(review.id)
    inputs = dict(refs)
    if review is not None:
        inputs["triggered_by"] = f"review_item_{review.status}"
    log_event(
        db=db,
        event_type="journal_entry_posted",
        source_type="journal_entry",
        source_id=entry.id,
        actor_type="human",
        actor_name=actor,
        input_snapshot=inputs,
        output_snapshot={
            **refs,
            "status": "posted",
            "gl_period": entry.entry_date.strftime("%Y-%m"),
            "document_id": str(entry.document_id) if entry.document_id else None,
        },
        rationale="Journal entry posted to general ledger.",
        document_id=entry.document_id,
        created_at=entry.posted_at,
    )


def post_directly(db: Session, journal_id: UUID) -> PostJournalEntryResponse:
    """Return a successful outcome only after journal, document and audit commit."""
    with _posting_transaction(db):
        entry, reviews = _lock_posting_rows(db, journal_id)
        _check_state(entry, None)
        _check_approvals(db, entry, reviews)
        _stage_post(db, entry, "api_user")
        _audit_post(db, entry, "api_user")
        return PostJournalEntryResponse(
            id=entry.id,
            status=entry.status,
            posted_at=entry.posted_at,
            trial_balance_status="balanced",
        )


def post_bookkeeping_review(
    db: Session,
    review: ReviewItem,
    resolution_note: str | None,
    edited_payload: dict[str, Any] | None = None,
) -> ReviewApproveResponse | ReviewEditResponse:
    with _posting_transaction(db):
        entry, reviews = _lock_review_target(db, review)
        _check_state(entry, review)
        replaced_lines = False
        if edited_payload is not None:
            try:
                replaced_lines = apply_journal_edits(db, entry, edited_payload)
            except ValueError as exc:
                raise JournalPostingError(
                    422, "journal_validation_failed", str(exc)
                ) from exc
        _check_approvals(db, entry, reviews, review, replaced_lines=replaced_lines)
        resolved_at = datetime.now(UTC)
        _stage_post(db, entry, "human_user")
        entry.posted_at = max(entry.posted_at, resolved_at + timedelta(microseconds=1))
        decision = "edited" if edited_payload is not None else "approved"
        review.status = decision
        review.resolution_note = resolution_note
        review.resolved_by = "human_user"
        review.resolved_at = resolved_at
        inputs: dict[str, Any] = {
            "review_type": review.review_type,
            "resolution_note": resolution_note,
        }
        if edited_payload is not None:
            review.edited_payload = edited_payload
            inputs["edited_payload"] = edited_payload
        log_event(
            db=db,
            event_type=f"review_item_{decision}",
            source_type="review_item",
            source_id=review.id,
            actor_type="human",
            actor_name=review.resolved_by,
            human_action=decision,
            input_snapshot=inputs,
            output_snapshot={
                "status": decision,
                "next_workflow_status": "posted",
                "journal_entry_id": str(entry.id),
            },
            document_id=entry.document_id,
            created_at=resolved_at,
        )
        _audit_post(db, entry, "human_user", review)
        response = (
            ReviewEditResponse if edited_payload is not None else ReviewApproveResponse
        )
        return response(
            id=review.id,
            status=decision,
            resolved_at=resolved_at,
            next_workflow_status="posted",
            message="Review item edited and approved."
            if edited_payload is not None
            else "Review item approved successfully.",
        )


def reject_bookkeeping_review(
    db: Session,
    review: ReviewItem,
    resolution_note: str | None,
) -> ReviewRejectResponse:
    with _posting_transaction(db):
        entry, _ = _lock_review_target(db, review)
        _check_state(entry, review, rejecting=True)
        document = entry.document
        if document is not None and document.status in {"posted", "voided", "rejected"}:
            raise _not_postable(entry, review)
        now = datetime.now(UTC)
        review.status = entry.status = "rejected"
        review.resolution_note = resolution_note
        review.resolved_by = "human_user"
        review.resolved_at = now
        if document is not None:
            document.status = "rejected"
        log_event(
            db=db,
            event_type="review_item_rejected",
            source_type="review_item",
            source_id=review.id,
            actor_type="human",
            actor_name=review.resolved_by,
            human_action="rejected",
            created_at=now,
            document_id=entry.document_id,
            input_snapshot={
                "review_type": review.review_type,
                "resolution_note": resolution_note,
            },
            output_snapshot={"status": "rejected", "journal_entry_id": str(entry.id)},
        )
        return ReviewRejectResponse(
            id=review.id,
            status=review.status,
            resolved_at=now,
            message="Review item rejected.",
        )
