"""Shared Audit Logging Service for ReconAI."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent


def log_event(
    db: Session,
    event_type: str,
    actor_type: str,
    source_type: str,
    source_id: uuid.UUID,
    actor_name: str | None = None,
    summary: str | None = None,
    input_snapshot: dict[str, Any] | list[Any] | None = None,
    output_snapshot: dict[str, Any] | list[Any] | None = None,
    rationale: str | None = None,
    confidence_score: float | None = None,
    human_action: str | None = None,
    document_id: uuid.UUID | str | None = None,
    created_at: datetime | None = None,
) -> AuditEvent:
    """Create and persist an AuditEvent record in a centralized, consistent manner.

    Preserves the existing AuditEvent model columns and attaches document_id to
    snapshots for cross-entity resolution if provided.

    Pass ``created_at`` explicitly when ordering matters within a single DB
    transaction (e.g. to guarantee review_item_approved sorts before any
    downstream pipeline events that are logged in the same request).
    """
    # Ensure document_id is attached into snapshots if provided and snapshot is a dict
    if document_id is not None:
        doc_id_str = str(document_id)
        if isinstance(input_snapshot, dict) and "document_id" not in input_snapshot:
            input_snapshot["document_id"] = doc_id_str
        if isinstance(output_snapshot, dict) and "document_id" not in output_snapshot:
            output_snapshot["document_id"] = doc_id_str

    final_rationale = rationale if rationale is not None else summary

    audit_event = AuditEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        actor_type=actor_type,
        actor_name=actor_name,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        rationale=final_rationale,
        confidence_score=confidence_score,
        human_action=human_action,
    )
    if created_at is not None:
        audit_event.created_at = created_at
    db.add(audit_event)
    return audit_event
