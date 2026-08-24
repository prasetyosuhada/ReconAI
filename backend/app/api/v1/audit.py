"""FastAPI Audit Events & Traceability API Router."""

import logging
import uuid
from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.document import Document
from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.schemas.audit import (
    AuditEventListResponse,
    AuditEventResponse,
    DocumentAuditTraceabilityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-events", tags=["Audit Events & Traceability"])
audit_log_router = APIRouter(prefix="/audit-log", tags=["Audit Events & Traceability"])


def _parse_filter_date(d_val: str | None, is_end: bool = False) -> datetime | None:
    if not d_val or not d_val.strip():
        return None
    d_str = d_val.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(d_str, fmt)
            if fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                parsed = datetime.combine(
                    parsed.date(),
                    time(23, 59, 59, 999999) if is_end else time(0, 0, 0),
                )
            return parsed
        except ValueError:
            continue
    return None


def _build_document_traceability(
    doc: Document,
    db: Session,
    resolved_entity_type: str = "document",
    resolved_entity_id: uuid.UUID | None = None,
) -> DocumentAuditTraceabilityResponse:
    """Helper to build full end-to-end timeline for a source document."""
    jes = db.query(JournalEntry).filter(JournalEntry.document_id == doc.id).all()
    je_uuids = [je.id for je in jes]

    doc_id_str = str(doc.id)
    conditions = [
        AuditEvent.source_id == doc.id,
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
    up_at = getattr(doc, "uploaded_at", None) or getattr(doc, "created_at", None)

    return DocumentAuditTraceabilityResponse(
        document_id=doc.id,
        filename=doc.original_filename,
        current_status=doc.status,
        uploaded_at=up_at,
        timeline=event_responses,
        resolved_entity_type=resolved_entity_type,
        resolved_entity_id=resolved_entity_id or doc.id,
    )


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

    return _build_document_traceability(
        doc, db, resolved_entity_type="document", resolved_entity_id=doc.id
    )


@audit_log_router.get(
    "/journal-entry/{journal_entry_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Trace audit log by Journal Entry UUID",
)
@router.get(
    "/journal-entry/{journal_entry_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Trace audit log by Journal Entry UUID",
    include_in_schema=False,
)
def get_journal_entry_audit_log(
    journal_entry_id: str,
    db: Session = Depends(get_db),
) -> DocumentAuditTraceabilityResponse:
    """Trace audit log starting from a Journal Entry."""
    try:
        je_uuid = uuid.UUID(journal_entry_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid journal entry UUID format.",
        ) from None

    je = db.query(JournalEntry).filter(JournalEntry.id == je_uuid).first()
    if not je:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry [{journal_entry_id}] not found.",
        )

    # If linked to a source document, return full document traceability
    if je.document_id:
        doc = db.query(Document).filter(Document.id == je.document_id).first()
        if doc:
            return _build_document_traceability(
                doc, db, resolved_entity_type="journal_entry", resolved_entity_id=je.id
            )

    # Manual or adjusting journal entry without source document
    je_id_str = str(je.id)
    conditions = [
        AuditEvent.source_id == je.id,
        AuditEvent.input_snapshot["journal_entry_id"].astext == je_id_str,
        AuditEvent.output_snapshot["journal_entry_id"].astext == je_id_str,
    ]
    events = (
        db.query(AuditEvent)
        .filter(or_(*conditions))
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    event_responses = [AuditEventResponse.model_validate(e) for e in events]

    return DocumentAuditTraceabilityResponse(
        document_id=None,
        filename=f"Journal Entry #{str(je.id)[:8]} ({je.description})",
        current_status=je.status,
        uploaded_at=je.created_at,
        timeline=event_responses,
        resolved_entity_type="journal_entry",
        resolved_entity_id=je.id,
    )


@audit_log_router.get(
    "/bank-transaction/{bank_transaction_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Trace audit log by Bank Transaction UUID",
)
@router.get(
    "/bank-transaction/{bank_transaction_id}",
    response_model=DocumentAuditTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Trace audit log by Bank Transaction UUID",
    include_in_schema=False,
)
def get_bank_transaction_audit_log(
    bank_transaction_id: str,
    db: Session = Depends(get_db),
) -> DocumentAuditTraceabilityResponse:
    """Trace audit log starting from a Bank Transaction."""
    try:
        tx_uuid = uuid.UUID(bank_transaction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bank transaction UUID format.",
        ) from None

    tx = db.query(BankTransaction).filter(BankTransaction.id == tx_uuid).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank transaction [{bank_transaction_id}] not found.",
        )

    # Resolution priority:
    # 1. Accepted ReconciliationMatch with journal_entry_id
    # 2. Most recent ReconciliationMatch with journal_entry_id
    matches = (
        db.query(ReconciliationMatch)
        .filter(
            ReconciliationMatch.bank_transaction_id == tx.id,
            ReconciliationMatch.journal_entry_id.isnot(None),
        )
        .order_by(
            (ReconciliationMatch.status == "accepted").desc(),
            ReconciliationMatch.created_at.desc(),
        )
        .all()
    )

    best_match = matches[0] if matches else None
    if best_match and best_match.journal_entry_id:
        je = (
            db.query(JournalEntry)
            .filter(JournalEntry.id == best_match.journal_entry_id)
            .first()
        )
        if je and je.document_id:
            doc = db.query(Document).filter(Document.id == je.document_id).first()
            if doc:
                return _build_document_traceability(
                    doc,
                    db,
                    resolved_entity_type="bank_transaction",
                    resolved_entity_id=tx.id,
                )

    # Unmatched bank transaction or matched to documentless JE
    tx_id_str = str(tx.id)
    conditions = [
        AuditEvent.source_id == tx.id,
        AuditEvent.input_snapshot["bank_transaction_id"].astext == tx_id_str,
        AuditEvent.output_snapshot["bank_transaction_id"].astext == tx_id_str,
    ]

    # Include parent batch bank_statement_imported event if available
    if tx.bank_statement_import_id:
        conditions.append(
            and_(
                AuditEvent.source_type == "bank_statement_import",
                AuditEvent.source_id == tx.bank_statement_import_id,
            )
        )

    # Also include any reconciliation match events for this bank transaction
    all_matches = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.bank_transaction_id == tx.id)
        .all()
    )
    match_ids = [m.id for m in all_matches]
    if match_ids:
        conditions.append(AuditEvent.source_id.in_(match_ids))

    events = (
        db.query(AuditEvent)
        .filter(or_(*conditions))
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    event_responses = [AuditEventResponse.model_validate(e) for e in events]

    up_at = getattr(tx, "created_at", None)
    if tx.import_record and getattr(tx.import_record, "imported_at", None):
        up_at = tx.import_record.imported_at

    return DocumentAuditTraceabilityResponse(
        document_id=None,
        filename=f"Bank Transaction #{str(tx.id)[:8]} ({tx.description})",
        current_status=tx.status,
        uploaded_at=up_at,
        timeline=event_responses,
        resolved_entity_type="bank_transaction",
        resolved_entity_id=tx.id,
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
    start_date: str | None = Query(
        None, description="Filter events created on or after date (YYYY-MM-DD or ISO)"
    ),
    end_date: str | None = Query(
        None, description="Filter events created on or before date (YYYY-MM-DD or ISO)"
    ),
    search: str | None = Query(
        None, description="Search event_type, actor_name, or rationale"
    ),
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> AuditEventListResponse:
    """Fetch paginated audit events with filtering and search."""
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

    # Date range filters
    parsed_start = _parse_filter_date(start_date, is_end=False)
    if parsed_start:
        query = query.filter(AuditEvent.created_at >= parsed_start)

    parsed_end = _parse_filter_date(end_date, is_end=True)
    if parsed_end:
        query = query.filter(AuditEvent.created_at <= parsed_end)

    # Search filter (case-insensitive across event_type, actor_name, rationale)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AuditEvent.event_type.ilike(term),
                AuditEvent.actor_name.ilike(term),
                AuditEvent.rationale.ilike(term),
            )
        )

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

