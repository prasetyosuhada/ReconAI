"""Pydantic Schemas for Document Endpoints."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """API response schema for uploaded document."""

    id: str = Field(..., description="UUID of the document")
    original_filename: str = Field(
        ..., description="Original filename of uploaded file"
    )
    document_type: str = Field(..., description="Document type e.g. invoice, receipt")
    status: str = Field(..., description="Current status e.g. uploaded, extracting")
    uploaded_at: datetime = Field(..., description="Upload timestamp in UTC")
    links: dict[str, str] = Field(
        default_factory=dict, description="Related hypermedia links"
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(BaseModel):
    """Detailed response schema for single document."""

    id: str
    original_filename: str
    stored_file_path: str
    mime_type: str
    file_size_bytes: int
    document_type: str
    status: str
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentExtractionResponse(BaseModel):
    """Structured extraction data persisted for a document."""

    id: str
    document_id: str
    vendor_name: str | None = None
    transaction_date: date | None = None
    subtotal_amount: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str = "IDR"
    line_items: dict[str, Any] | list[Any] | None = None
    provider_metadata: dict[str, Any] | None = None
    confidence_score: float = 0.0
    rationale: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    items: list[DocumentDetailResponse]
    total: int
    limit: int
    offset: int
