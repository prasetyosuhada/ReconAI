"""Pydantic Schemas for Review Items Endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewItemListItemResponse(BaseModel):
    """API response schema for item in review items list."""

    id: uuid.UUID = Field(..., description="UUID of the review item")
    review_type: str = Field(
        ...,
        description="Type: extraction, bookkeeping, reconciliation, validation",
    )
    status: str = Field(
        ..., description="Status: pending, approved, edited, rejected, cancelled"
    )
    priority: str = Field(..., description="Priority: low, normal, high")
    source_type: str = Field(
        ..., description="Source type e.g. document, journal_entry, bank_transaction"
    )
    source_id: uuid.UUID = Field(..., description="UUID of source record")
    title: str = Field(..., description="Title of review item")
    summary: str | None = Field(
        None, description="Detailed summary of why review is needed"
    )
    suggested_action: str | None = Field(
        None, description="Suggested action for human reviewer"
    )
    created_at: datetime = Field(..., description="Creation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


class ReviewItemListResponse(BaseModel):
    """Paginated list envelope response for review items."""

    items: list[ReviewItemListItemResponse] = Field(
        ..., description="List of review items"
    )
    total: int = Field(..., description="Total count matching filters")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


class ReviewItemDetailResponse(BaseModel):
    """API response schema for detailed review item."""

    id: uuid.UUID = Field(..., description="UUID of the review item")
    review_type: str = Field(..., description="Type of review")
    status: str = Field(..., description="Status")
    priority: str = Field(..., description="Priority: low, normal, high")
    source_type: str = Field(..., description="Source type")
    source_id: uuid.UUID = Field(..., description="UUID of source record")
    title: str = Field(..., description="Title of review item")
    summary: str | None = Field(None, description="Detailed summary")
    suggested_action: str | None = Field(None, description="Suggested action")
    original_payload: dict[str, Any] | list[Any] | None = Field(
        None, description="Original agent state payload"
    )
    edited_payload: dict[str, Any] | list[Any] | None = Field(
        None, description="Human edited payload if any"
    )
    resolution_note: str | None = Field(None, description="Resolution rationale note")
    resolved_by: str | None = Field(
        None, description="User identifier who resolved review"
    )
    resolved_at: datetime | None = Field(None, description="Resolution timestamp")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last update timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)
