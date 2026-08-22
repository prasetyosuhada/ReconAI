"""FastAPI Audit Events & Traceability API Router."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.document import Document
from app.models.journal import JournalEntry
from app.schemas.audit import (
    AuditEventListResponse,
    AuditEventResponse,
    DocumentAuditTraceabilityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-events", tags=["Audit Events & Traceability"])
audit_log_router = APIRouter(prefix="/audit-log", tags=["Audit Events & Traceability"])


@audit_log_router.get(
    "/{document_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full audit traceability timeline for a document",
)
@router.get(
    "/document/{document_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get audit log timeline for a document",
    include_in_schema=False,
)
def get_document_audit_log(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentAuditTraceabilityResponse:
    """Fetch complete end-to-end audit traceability log for a source document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document UUID format.",
        ) from None

    doc = db.query(Document).filter(Document.id == doc_uuid).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document [{document_id}] not found.",
        )

    # Find associated journal entries
    jes = db.query(JournalEntry).filter(JournalEntry.document_id == doc_uuid).all()
    je_uuids = [je.id for je in jes]

    # Query audit events related to document or its journal entries
    # Matches any of:
    # 1. source_id == document_id (e.g. document_uploaded, extraction_completed)
    # 2. source_id IN (journal_entry_ids for this document) (e.g. bookkeeping_completed, journal_entry_posted)
    # 3. input_snapshot->>'document_id' == document_id (e.g. review_item_approved/edited/rejected, reconciliation_match_*)
    # 4. output_snapshot->>'document_id' == document_id
    doc_id_str = str(doc_uuid)
    conditions = [
        AuditEvent.source_id == doc_uuid,
        AuditEvent.input_snapshot["document_id"].astext == doc_id_str,
        AuditEvent.output_snapshot["document_id"].astext == doc_id_str,
    ]
    if je_uuids:
        conditions.append(AuditEvent.source_id.in_(je_uuids))

    events = (
        db.query(AuditEvent)
        .filter(or_(*conditions))
        .order_by(AuditEvent.created_at.asc())
        .all()
    )

    event_responses = [AuditEventResponse.model_validate(e) for e in events]

    return DocumentAuditTraceabilityResponse(
        document_id=doc.id,
        filename=doc.original_filename,
        current_status=doc.status,
        uploaded_at=doc.created_at,
        timeline=event_responses,
    )


@router.get(
    "",
    response_model=AuditEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all audit events",
)
def list_audit_events(
    source_type: str | None = Query(
        None, description="Filter by source_type (e.g. document, journal_entry)"
    ),
    source_id: str | None = Query(None, description="Filter by source entity UUID"),
    event_type: str | None = Query(
        None, description="Filter by event_type (e.g. document_uploaded)"
    ),
    actor_type: str | None = Query(
        None, description="Filter by actor_type (agent, human, system)"
    ),
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> AuditEventListResponse:
    """Fetch paginated audit events with filtering."""
    query = db.query(AuditEvent)

    if source_type:
        query = query.filter(AuditEvent.source_type == source_type)

    if source_id:
        try:
            s_uuid = uuid.UUID(source_id)
            query = query.filter(AuditEvent.source_id == s_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source_id UUID format.",
            ) from None

    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)

    if actor_type:
        query = query.filter(AuditEvent.actor_type == actor_type)

    total_count = query.with_entities(func.count(AuditEvent.id)).scalar() or 0

    events = (
        query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()
    )

    items = [AuditEventResponse.model_validate(e) for e in events]

    return AuditEventListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{audit_event_id}",
    response_model=AuditEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single audit event details",
)
def get_audit_event_detail(
    audit_event_id: str,
    db: Session = Depends(get_db),
) -> AuditEventResponse:
    """Fetch detail of a single audit event."""
    try:
        event_uuid = uuid.UUID(audit_event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audit_event_id UUID format.",
        ) from None

    event = db.query(AuditEvent).filter(AuditEvent.id == event_uuid).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit event [{audit_event_id}] not found.",
        )

    return AuditEventResponse.model_validate(event)
