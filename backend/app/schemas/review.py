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

    # Convenience fields populated from original_payload for the frontend modals.
    # These guarantee consistency: both GL modal and Review Queue modal read the
    # same values from a single authoritative source.
    confidence_score: float | None = Field(
        None, description="AI confidence score extracted from payload"
    )
    risk_flags: list[str] = Field(
        default_factory=list, description="AI risk flags extracted from payload"
    )
    journal_entry_id: str | None = Field(
        None,
        description="UUID of the linked JournalEntry (for bookkeeping reviews)",
    )

    model_config = ConfigDict(from_attributes=True)



class ReviewApproveRequest(BaseModel):
    """Request schema for approving a review item."""

    resolution_note: str | None = Field(
        None, description="Optional rationale/note for approval"
    )


class ReviewApproveResponse(BaseModel):
    """Response schema after approving a review item."""

    id: uuid.UUID = Field(..., description="UUID of the review item")
    status: str = Field(..., description="New status: approved")
    resolved_at: datetime = Field(..., description="Resolution timestamp")
    next_workflow_status: str = Field(
        ..., description="Updated status of underlying source entity"
    )
    message: str = Field(..., description="Summary response message")


class ReviewEditRequest(BaseModel):
    """Request schema for editing and approving a review item."""

    edited_payload: dict[str, Any] = Field(
        ..., description="Edited data parameters overriding original payload"
    )
    resolution_note: str | None = Field(
        None, description="Optional note explaining human edit"
    )


class ReviewEditResponse(BaseModel):
    """Response schema after editing a review item."""

    id: uuid.UUID = Field(..., description="UUID of the review item")
    status: str = Field(..., description="New status: edited")
    resolved_at: datetime = Field(..., description="Resolution timestamp")
    next_workflow_status: str = Field(
        ..., description="Updated status of underlying entity"
    )
    message: str = Field(..., description="Summary response message")


class ReviewRejectRequest(BaseModel):
    """Request schema for rejecting a review item."""

    resolution_note: str | None = Field(
        None, description="Rationale/note explaining rejection"
    )


class ReviewRejectResponse(BaseModel):
    """Response schema after rejecting a review item."""

    id: uuid.UUID = Field(..., description="UUID of the review item")
    status: str = Field(..., description="New status: rejected")
    resolved_at: datetime = Field(..., description="Resolution timestamp")
    message: str = Field(..., description="Summary response message")
