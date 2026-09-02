"""Shared persistence for normalized bookkeeping outcomes."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.schemas import BookkeepingOutcome
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.accounting import save_journal_entry_safely


class BookkeepingPersistenceResult(BaseModel):
    """Database-side result used by initial and review-continuation wrappers."""

    success: bool
    status: str
    journal_entry_id: uuid.UUID | None = None
    review_item_id: uuid.UUID | None = None
    review_item_created: bool = False
    journal_entry_date: date
    journal_description: str
    decision: str = "Bookkeeping classified"
    reasoning: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def load_active_chart_of_accounts(db: Session) -> list[dict[str, Any]]:
    """Return the active COA as the plain payload consumed by bookkeeping."""
    coa_records = (
        db.query(ChartOfAccount)
        .filter(ChartOfAccount.is_active.is_(True))
        .order_by(ChartOfAccount.account_code)
        .all()
    )
    return [
        {
            "account_code": coa.account_code,
            "account_name": coa.account_name,
            "account_type": coa.account_type,
            "normal_balance": coa.normal_balance,
            "is_sensitive": coa.is_sensitive,
            "description": coa.description,
        }
        for coa in coa_records
    ]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _audit_summary(outcome: BookkeepingOutcome) -> tuple[str, list[str]]:
    decision = "Bookkeeping classified"
    debit_lines = [
        f"COA: {line.get('account_code')} - {line.get('account_name', '')}".strip(" -")
        for line in outcome.journal_lines
        if float(line.get("debit_amount", 0.0) or 0.0) > 0
    ]
    if debit_lines:
        decision = debit_lines[0]

    reasoning = [outcome.rationale] if outcome.rationale else []
    reasoning.extend(f"Risk flag: {flag}" for flag in outcome.risk_flags)
    return decision, reasoning


def persist_bookkeeping_outcome(
    db: Session,
    document: Document,
    extraction: DocumentExtraction,
    outcome: BookkeepingOutcome,
) -> BookkeepingPersistenceResult:
    """Persist one bookkeeping outcome without committing the caller's transaction."""
    entry_date = (
        _parse_date(outcome.entry_date) or extraction.transaction_date or date.today()
    )
    description = (
        outcome.entry_description or f"Journal for {document.original_filename}"
    )
    decision, reasoning = _audit_summary(outcome)

    if not outcome.journal_lines:
        document.status = "failed"
        return BookkeepingPersistenceResult(
            success=False,
            status="failed",
            journal_entry_date=entry_date,
            journal_description=description,
            decision=decision,
            reasoning=reasoning,
            errors=["Bookkeeping outcome contains no journal lines."],
        )

    existing_journal = (
        db.query(JournalEntry)
        .filter(JournalEntry.document_id == document.id)
        .order_by(JournalEntry.created_at.desc())
        .first()
    )

    if existing_journal is not None and existing_journal.status in {
        "posted",
        "voided",
        "rejected",
    }:
        document.status = existing_journal.status
        return BookkeepingPersistenceResult(
            success=True,
            status=existing_journal.status,
            journal_entry_id=existing_journal.id,
            journal_entry_date=existing_journal.entry_date,
            journal_description=existing_journal.description,
            decision=decision,
            reasoning=reasoning,
        )

    coa_payload = load_active_chart_of_accounts(db)
    journal_data = {
        "document_id": document.id,
        "extraction_id": extraction.id,
        "entry_date": entry_date,
        "description": description,
        "status": "review_required" if outcome.needs_review else "draft",
        "source_type": "document",
        "agent_name": "BookkeepingAgent",
        "confidence_score": outcome.confidence_score,
        "rationale": outcome.rationale,
        "risk_flags": outcome.risk_flags,
        "lines": outcome.journal_lines,
    }
    save_result = save_journal_entry_safely(
        journal_data,
        db_session=db,
        chart_of_accounts=coa_payload,
        existing_entry=existing_journal,
    )
    if not save_result.success or not save_result.journal_entry_id:
        document.status = "failed"
        return BookkeepingPersistenceResult(
            success=False,
            status="failed",
            journal_entry_date=entry_date,
            journal_description=description,
            decision=decision,
            reasoning=reasoning,
            errors=save_result.errors,
        )

    journal_id = uuid.UUID(save_result.journal_entry_id)
    review_item_id: uuid.UUID | None = None
    review_item_created = False
    review_required = (
        outcome.needs_review
        or outcome.status == "bookkeeping_review_required"
        or bool(outcome.risk_flags)
    )

    if review_required:
        is_sensitive = outcome.uses_sensitive_account or (
            "uses_sensitive_account" in outcome.risk_flags
        )
        priority = "high" if is_sensitive or not outcome.is_balanced else "normal"
        flags = ", ".join(outcome.risk_flags) if outcome.risk_flags else "None"
        review_payload = {
            "journal_entry_id": str(journal_id),
            "vendor_name": extraction.vendor_name,
            "transaction_date": str(extraction.transaction_date or ""),
            "total_amount": _optional_float(extraction.total_amount),
            "subtotal_amount": _optional_float(extraction.subtotal_amount),
            "tax_amount": _optional_float(extraction.tax_amount),
            "currency": extraction.currency,
            "line_items": extraction.line_items or [],
            "lines": outcome.journal_lines,
            "entry_date": str(entry_date),
            "description": description,
            "rationale": outcome.rationale,
            "risk_flags": outcome.risk_flags,
            "confidence_score": outcome.confidence_score,
            "is_balanced": outcome.is_balanced,
            "uses_sensitive_account": outcome.uses_sensitive_account,
        }
        review_item = (
            db.query(ReviewItem)
            .filter(
                ReviewItem.source_type == "journal_entry",
                ReviewItem.source_id == journal_id,
                ReviewItem.review_type == "bookkeeping",
                ReviewItem.status == "pending",
            )
            .first()
        )
        if review_item is None:
            candidate = ReviewItem(
                id=uuid.uuid4(),
                review_type="bookkeeping",
                status="pending",
                priority=priority,
                source_type="journal_entry",
                source_id=journal_id,
                title=f"Review Needed: {document.original_filename}",
                summary=(
                    f"Agent flagged document. Conf: {outcome.confidence_score:.2f}, "
                    f"Flags: {flags}"
                ),
                suggested_action=(
                    "Review the AI-generated journal entry account classification."
                ),
                original_payload=review_payload,
            )
            try:
                with db.begin_nested():
                    db.add(candidate)
                    db.flush()
                review_item = candidate
                review_item_created = True
            except IntegrityError:
                review_item = (
                    db.query(ReviewItem)
                    .filter(
                        ReviewItem.source_type == "journal_entry",
                        ReviewItem.source_id == journal_id,
                        ReviewItem.review_type == "bookkeeping",
                        ReviewItem.status == "pending",
                    )
                    .one()
                )

        if not review_item_created:
            review_item.priority = priority
            review_item.summary = (
                f"Agent flagged document. Conf: {outcome.confidence_score:.2f}, "
                f"Flags: {flags}"
            )
            review_item.original_payload = review_payload
        db.flush()
        review_item_id = review_item.id

    document.status = outcome.status
    db.flush()
    return BookkeepingPersistenceResult(
        success=True,
        status=outcome.status,
        journal_entry_id=journal_id,
        review_item_id=review_item_id,
        review_item_created=review_item_created,
        journal_entry_date=entry_date,
        journal_description=description,
        decision=decision,
        reasoning=reasoning,
    )
