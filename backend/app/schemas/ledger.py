"""Pydantic Schemas for Ledger Endpoints."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JournalLineResponse(BaseModel):
    """API response schema for a single line in a journal entry."""

    id: uuid.UUID = Field(..., description="UUID of the line")
    line_number: int = Field(..., description="Line number sequence starting at 1")
    account_id: uuid.UUID = Field(..., description="UUID of associated COA")
    account_code: str = Field(..., description="Account code e.g. 5100")
    account_name: str = Field(..., description="Account name e.g. Office Supplies")
    debit_amount: float = Field(..., description="Debit amount (>= 0.00)")
    credit_amount: float = Field(..., description="Credit amount (>= 0.00)")
    description: str | None = Field(None, description="Line item description")

    model_config = ConfigDict(from_attributes=True)


class JournalEntryListItemResponse(BaseModel):
    """API response schema for item in list_journal_entries."""

    id: uuid.UUID = Field(..., description="UUID of journal entry")
    document_id: uuid.UUID | None = Field(None, description="Document UUID")
    extraction_id: uuid.UUID | None = Field(None, description="Extraction UUID")
    entry_date: date = Field(..., description="Transaction entry date")
    description: str = Field(..., description="Header description")
    status: str = Field(
        ..., description="Status: draft, review_required, approved, posted"
    )
    agent_name: str | None = Field(None, description="Agent name")
    confidence_score: float | None = Field(None, description="Confidence score")
    total_debit: float = Field(..., description="Sum of debit amounts")
    total_credit: float = Field(..., description="Sum of credit amounts")
    posted_at: datetime | None = Field(None, description="Posting timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class JournalEntryListResponse(BaseModel):
    """Paginated response envelope for journal entries."""

    items: list[JournalEntryListItemResponse] = Field(
        ..., description="Journal entry items"
    )
    total: int = Field(..., description="Total count matching filters")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


class JournalEntryDetailResponse(BaseModel):
    """API response schema for detailed journal entry with lines."""

    id: uuid.UUID = Field(..., description="UUID of journal entry")
    document_id: uuid.UUID | None = Field(None, description="Document UUID")
    extraction_id: uuid.UUID | None = Field(None, description="Extraction UUID")
    entry_date: date = Field(..., description="Entry date")
    description: str = Field(..., description="Header description")
    status: str = Field(..., description="Status")
    agent_name: str | None = Field(None, description="Agent name")
    confidence_score: float | None = Field(None, description="Confidence score")
    rationale: str | None = Field(None, description="Rationale explanation")
    risk_flags: list[Any] | None = Field(None, description="Risk flags")
    lines: list[JournalLineResponse] = Field(
        default_factory=list, description="Journal lines"
    )
    posted_at: datetime | None = Field(None, description="Posting timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class ChartOfAccountResponse(BaseModel):
    """API response schema for Chart of Account item."""

    id: uuid.UUID = Field(..., description="UUID of COA")
    account_code: str = Field(..., description="Account code e.g. 1010")
    account_name: str = Field(..., description="Account name")
    account_type: str = Field(
        ..., description="Type: asset, liability, equity, revenue, expense"
    )
    normal_balance: str = Field(..., description="Normal balance: debit, credit")
    is_sensitive: bool = Field(
        ..., description="True if sensitive account requiring review"
    )
    is_active: bool = Field(..., description="True if account is active")

    model_config = ConfigDict(from_attributes=True)


class ChartOfAccountListResponse(BaseModel):
    """Paginated response envelope for Chart of Accounts."""

    items: list[ChartOfAccountResponse] = Field(..., description="COA items")
    total: int = Field(..., description="Total count")
    limit: int = Field(..., description="Limit")
    offset: int = Field(..., description="Offset")


class TrialBalanceAccountBalance(BaseModel):
    """Account balance item in trial balance report."""

    account_code: str = Field(...)
    account_name: str = Field(...)
    account_type: str = Field(...)
    debit_balance: float = Field(...)
    credit_balance: float = Field(...)


class TrialBalanceResponse(BaseModel):
    """API response schema for Trial Balance report."""

    as_of_date: date = Field(...)
    status: str = Field(..., description="status: balanced or unbalanced")
    total_debits: float = Field(...)
    total_credits: float = Field(...)
    difference: float = Field(...)
    accounts: list[TrialBalanceAccountBalance] = Field(default_factory=list)


class PostJournalEntryResponse(BaseModel):
    """API response schema for posting a journal entry to ledger."""

    id: uuid.UUID = Field(..., description="UUID of journal entry")
    status: str = Field(..., description="Updated status e.g. posted")
    posted_at: datetime = Field(..., description="Timestamp when posted")
    trial_balance_status: str = Field(..., description="balanced or unbalanced")
