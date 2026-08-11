"""Pydantic Schemas for Audit Events / Traceability API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventResponse(BaseModel):
    """API response schema for a single audit event."""

    id: uuid.UUID
    event_type: str = Field(
        ..., description="e.g. document_uploaded, extraction_completed"
    )
    source_type: str = Field(
        ..., description="e.g. document, journal_entry, bank_statement"
    )
    source_id: uuid.UUID
    actor_type: str = Field(..., description="agent, human, system")
    actor_name: str | None = None
    input_snapshot: dict[str, Any] | list[Any] | None = None
    output_snapshot: dict[str, Any] | list[Any] | None = None
    rationale: str | None = None
    confidence_score: float | None = None
    human_action: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditEventListResponse(BaseModel):
    """Paginated response envelope for audit events."""

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


class DocumentAuditTraceabilityResponse(BaseModel):
    """Full end-to-end traceability response for a single document."""

    document_id: uuid.UUID
    filename: str
    current_status: str
    uploaded_at: datetime
    timeline: list[AuditEventResponse] = Field(
        default_factory=list, description="Chronological list of audit events"
    )
