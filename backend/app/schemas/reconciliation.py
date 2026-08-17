"""Pydantic Schemas for Reconciliation Endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReconcileRunRequest(BaseModel):
    """Request schema to trigger reconciliation workflow."""

    bank_statement_import_id: uuid.UUID = Field(
        ..., description="UUID of the bank statement import to reconcile"
    )


class ReconcileRunResponse(BaseModel):
    """API response schema after triggering reconciliation."""

    bank_statement_import_id: uuid.UUID = Field(...)
    status: str = Field(..., description="Status e.g. matching_in_progress")
    message: str = Field(...)


class BankTxNestedResponse(BaseModel):
    """Nested schema for bank transaction in match response."""

    id: uuid.UUID
    transaction_date: date
    description: str
    amount: float
    currency: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class JournalEntryNestedResponse(BaseModel):
    """Nested schema for journal entry in match response."""

    id: uuid.UUID
    entry_date: date
    description: str

    model_config = ConfigDict(from_attributes=True)


class ReconciliationMatchResponse(BaseModel):
    """API response schema for a reconciliation match."""

    id: uuid.UUID
    bank_transaction_id: uuid.UUID
    journal_entry_id: uuid.UUID | None = None
    bank_transaction: BankTxNestedResponse | None = None
    journal_entry: JournalEntryNestedResponse | None = None
    match_type: str = Field(..., description="exact, fuzzy, manual")
    status: str = Field(
        ..., description="proposed, accepted, rejected, review_required"
    )
    confidence_score: float = Field(...)
    amount_score: float | None = None
    date_score: float | None = None
    vendor_score: float | None = None
    rationale: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReconciliationMatchListResponse(BaseModel):
    """Paginated response envelope for reconciliation matches."""

    items: list[ReconciliationMatchResponse]
    total: int
    limit: int
    offset: int


class MatchActionRequest(BaseModel):
    """Request schema for accepting/rejecting a reconciliation match."""

    resolution_note: str | None = Field(None, description="Note explaining decision")


class MatchActionResponse(BaseModel):
    """Response schema after accepting or rejecting a match."""

    id: uuid.UUID
    status: str
    resolved_at: datetime
    message: str


class ReconciliationSummaryResponse(BaseModel):
    """API response schema for bank reconciliation summary."""

    bank_statement_import_id: uuid.UUID
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    bank_statement_balance: float
    gl_balance: float
    difference: float
    is_balanced: bool
    status: str  # reconciled, review_required, partially_reconciled, unreconciled
    total_transactions: int
    matched_count: int
    proposed_count: int
    unmatched_count: int
    gl_only_count: int
    progress_percentage: int


class ManualMatchRequest(BaseModel):
    """Request schema for manually linking a bank transaction to a journal entry."""

    bank_transaction_id: uuid.UUID
    journal_entry_id: uuid.UUID
    resolution_note: str | None = Field(
        None, description="Optional explanation for manual match"
    )

