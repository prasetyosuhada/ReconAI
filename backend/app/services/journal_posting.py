"""Eligibility checks and transaction ownership for direct ledger posting."""

import logging
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.schemas.ledger import PostJournalEntryResponse
from app.services.accounting import (
    CONFIDENCE_THRESHOLD_BOOKKEEPING,
    check_sensitive_accounts,
    post_journal_entry_to_ledger,
)
from app.services.audit_service import log_event

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


class ReviewedLine(BaseModel):
    account_code: str
    debit_amount: Decimal = Decimal(0)
    credit_amount: Decimal = Decimal(0)
    description: str | None = None


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


def _review_targets_entry(db: Session, entry: JournalEntry, review: ReviewItem) -> bool:
    """A document review can belong to a sibling journal, or predate journal IDs."""
    targets = set()
    for payload in (review.original_payload, review.edited_payload):
        if isinstance(payload, dict) and "journal_entry_id" in payload:
            try:
                targets.add(UUID(str(payload["journal_entry_id"])))
            except ValueError:
                raise _not_postable(entry, review) from None

    if review.source_type == "journal_entry":
        if targets and targets != {entry.id}:
            raise _not_postable(entry, review)
        return True

    if targets == {entry.id}:
        return True
    if len(targets) == 1:
        sibling = db.get(JournalEntry, targets.pop())
        if sibling is not None and sibling.document_id == entry.document_id:
            return False
    elif not targets:
        sibling_exists = (
            db.query(JournalEntry.id)
            .filter(
                JournalEntry.document_id == entry.document_id,
                JournalEntry.id != entry.id,
            )
            .first()
        )
        if sibling_exists is None:
            return True
    raise _not_postable(entry, review)


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


def _check_direct_post(db: Session, entry: JournalEntry) -> None:
    if entry.status == "posted":
        raise JournalPostingError(
            409,
            "journal_already_posted",
            "This journal is already posted. Refresh the journal.",
            entry.status,
        )
    if entry.status == "review_required":
        raise _review_required(entry)
    if entry.status not in {"draft", "approved"} or entry.source_type not in {
        "document",
        "manual",
        "import",
        "system",
    }:
        raise _not_postable(entry)

    source = and_(
        ReviewItem.source_type == "journal_entry", ReviewItem.source_id == entry.id
    )
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
        if document.status in {
            "extraction_review_required",
            "bookkeeping_review_required",
        }:
            raise _review_required(entry)
        if document.status != "ready_to_post" and not (
            document.status == "approved" and entry.status == "approved"
        ):
            raise _not_postable(entry)
        source = or_(source, document_source)
    elif entry.status == "draft" and entry.source_type == "document":
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
    reviews = db.query(ReviewItem).filter(
        source, ReviewItem.review_type == "bookkeeping"
    )
    for review in reviews.order_by(ReviewItem.id):
        if not _review_targets_entry(db, entry, review):
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


def post_directly(db: Session, journal_id: UUID) -> PostJournalEntryResponse:
    """Return a successful outcome only after journal, document and audit commit."""
    try:
        entry = db.get(JournalEntry, journal_id)
        if entry is None:
            raise JournalPostingError(404, "not_found", "Journal entry not found.")
        _check_direct_post(db, entry)
        posted = post_journal_entry_to_ledger(entry, db, posted_by="api_user")
        if not posted.success:
            raise JournalPostingError(
                422, "journal_validation_failed", " ".join(posted.errors)
            )

        if entry.document is not None:
            entry.document.status = "posted"
        log_event(
            db=db,
            event_type="journal_entry_posted",
            source_type="journal_entry",
            source_id=entry.id,
            actor_type="human",
            actor_name="api_user",
            input_snapshot={"journal_entry_id": str(entry.id)},
            output_snapshot={
                "status": "posted",
                "journal_entry_id": str(entry.id),
                "gl_period": entry.entry_date.strftime("%Y-%m"),
                "document_id": str(entry.document_id) if entry.document_id else None,
            },
            rationale="Journal entry posted to general ledger.",
            document_id=entry.document_id,
            created_at=entry.posted_at,
        )
        response = PostJournalEntryResponse(
            id=entry.id,
            status=entry.status,
            posted_at=entry.posted_at,
            trial_balance_status="balanced",
        )
        db.commit()
        return response
    except JournalPostingError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Direct posting failed for journal %s", journal_id)
        raise JournalPostingError(
            503,
            "posting_failed",
            "Posting could not be confirmed. Refresh the journal before retrying.",
        ) from exc
