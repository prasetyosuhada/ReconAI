"""Pydantic Schemas for Bank Statement Import Endpoints."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BankStatementImportResponse(BaseModel):
    """API response schema for bank statement CSV upload/import."""

    id: uuid.UUID = Field(..., description="UUID of bank statement import")
    original_filename: str = Field(..., description="Original CSV filename")
    status: str = Field(
        ..., description="Status e.g. imported, partially_matched, matched"
    )
    row_count: int = Field(..., description="Number of parsed transactions")
    imported_at: datetime = Field(..., description="Import timestamp in UTC")
    links: dict[str, str] = Field(default_factory=dict, description="Related API links")

    model_config = ConfigDict(from_attributes=True)


class BankStatementImportListItemResponse(BaseModel):
    """API response schema for item in list_bank_statements."""

    id: uuid.UUID = Field(...)
    original_filename: str = Field(...)
    status: str = Field(...)
    row_count: int = Field(...)
    imported_at: datetime = Field(...)

    model_config = ConfigDict(from_attributes=True)


class BankStatementImportListResponse(BaseModel):
    """Paginated response envelope for bank statements."""

    items: list[BankStatementImportListItemResponse] = Field(...)
    total: int = Field(...)
    limit: int = Field(...)
    offset: int = Field(...)


class BankTransactionResponse(BaseModel):
    """API response schema for a single bank transaction."""

    id: uuid.UUID = Field(...)
    bank_statement_import_id: uuid.UUID = Field(...)
    transaction_date: date = Field(...)
    description: str = Field(...)
    amount: float = Field(...)
    currency: str = Field(...)
    reference_number: str | None = Field(None)
    status: str = Field(..., description="Status: imported, matched, unmatched")

    model_config = ConfigDict(from_attributes=True)


class BankTransactionListResponse(BaseModel):
    """Paginated response envelope for bank transactions."""

    items: list[BankTransactionResponse] = Field(...)
    total: int = Field(...)
    limit: int = Field(...)
    offset: int = Field(...)
