"""FastAPI Reconciliation API Router."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.schemas.reconciliation import (
    MatchActionRequest,
    MatchActionResponse,
    ReconcileRunRequest,
    ReconcileRunResponse,
    ReconciliationMatchListResponse,
    ReconciliationMatchResponse,
)
from app.services.reconciliation import execute_reconciliation_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])
reconcile_router = APIRouter(prefix="/reconcile", tags=["Reconciliation"])


@router.post(
    "/run",
    response_model=ReconcileRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Bank Reconciliation workflow",
)
@reconcile_router.post(
    "/run",
    response_model=ReconcileRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run Bank Reconciliation workflow",
)
def run_reconciliation_workflow(
    request: ReconcileRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ReconcileRunResponse:
    """Trigger background reconciliation matching workflow."""
    import_record = (
        db.query(BankStatementImport)
        .filter(BankStatementImport.id == request.bank_statement_import_id)
        .first()
    )
    if not import_record:
        imp_id_str = str(request.bank_statement_import_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank statement import [{imp_id_str}] not found.",
        )

    # Schedule background task
    background_tasks.add_task(
        execute_reconciliation_workflow, request.bank_statement_import_id
    )

    return ReconcileRunResponse(
        bank_statement_import_id=request.bank_statement_import_id,
        status="matching_in_progress",
        message="Reconciliation workflow started.",
    )


@router.get(
    "",
    response_model=ReconciliationMatchListResponse,
    status_code=status.HTTP_200_OK,
    summary="List reconciliation match results",
)
@router.get(
    "/matches",
    response_model=ReconciliationMatchListResponse,
    status_code=status.HTTP_200_OK,
    summary="List reconciliation matches",
    include_in_schema=False,
)
def list_reconciliation_matches(
    bank_statement_import_id: str | None = Query(
        None, description="Filter by bank statement import UUID"
    ),
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by status (proposed, accepted, rejected)",
    ),
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> ReconciliationMatchListResponse:
    """Fetch paginated list of reconciliation matches."""
    query = db.query(ReconciliationMatch).options(
        joinedload(ReconciliationMatch.bank_transaction),
        joinedload(ReconciliationMatch.journal_entry),
    )

    if bank_statement_import_id:
        try:
            imp_uuid = uuid.UUID(bank_statement_import_id)
            query = query.join(ReconciliationMatch.bank_transaction).filter(
                BankTransaction.bank_statement_import_id == imp_uuid
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bank_statement_import_id UUID format.",
            ) from None

    if status_filter:
        query = query.filter(ReconciliationMatch.status == status_filter)

    total_count = query.with_entities(func.count(ReconciliationMatch.id)).scalar() or 0

    matches = (
        query.order_by(ReconciliationMatch.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return ReconciliationMatchListResponse(
        items=matches,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{reconciliation_match_id}",
    response_model=ReconciliationMatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a reconciliation match",
)
def get_reconciliation_match(
    reconciliation_match_id: str,
    db: Session = Depends(get_db),
) -> ReconciliationMatchResponse:
    """Fetch single reconciliation match by UUID."""
    try:
        match_uuid = uuid.UUID(reconciliation_match_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reconciliation_match_id UUID format.",
        ) from None

    match = (
        db.query(ReconciliationMatch)
        .options(
            joinedload(ReconciliationMatch.bank_transaction),
            joinedload(ReconciliationMatch.journal_entry),
        )
        .filter(ReconciliationMatch.id == match_uuid)
        .first()
    )

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation match [{reconciliation_match_id}] not found.",
        )

    return match


@router.post(
    "/{reconciliation_match_id}/accept",
    response_model=MatchActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept a proposed reconciliation match",
)
def accept_reconciliation_match(
    reconciliation_match_id: str,
    action_req: MatchActionRequest | None = None,
    db: Session = Depends(get_db),
) -> MatchActionResponse:
    """Manually accept a proposed reconciliation match."""
    try:
        match_uuid = uuid.UUID(reconciliation_match_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reconciliation_match_id UUID format.",
        ) from None

    match = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.id == match_uuid)
        .first()
    )
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation match [{reconciliation_match_id}] not found.",
        )

    match.status = "accepted"
    match.updated_at = datetime.now(UTC)

    if match.bank_transaction:
        match.bank_transaction.status = "matched"

    note = action_req.resolution_note if action_req else None
    audit = AuditEvent(
        event_type="reconciliation_match_accepted",
        source_type="reconciliation_match",
        source_id=match.id,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={"resolution_note": note},
        output_snapshot={"status": "accepted"},
    )
    db.add(audit)
    db.commit()

    return MatchActionResponse(
        id=match.id,
        status="accepted",
        resolved_at=match.updated_at,
        message="Reconciliation match accepted.",
    )


@router.post(
    "/{reconciliation_match_id}/reject",
    response_model=MatchActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject a proposed reconciliation match",
)
def reject_reconciliation_match(
    reconciliation_match_id: str,
    action_req: MatchActionRequest | None = None,
    db: Session = Depends(get_db),
) -> MatchActionResponse:
    """Manually reject a proposed reconciliation match."""
    try:
        match_uuid = uuid.UUID(reconciliation_match_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reconciliation_match_id UUID format.",
        ) from None

    match = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.id == match_uuid)
        .first()
    )
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation match [{reconciliation_match_id}] not found.",
        )

    match.status = "rejected"
    match.updated_at = datetime.now(UTC)

    if match.bank_transaction:
        match.bank_transaction.status = "imported"

    note = action_req.resolution_note if action_req else None
    audit = AuditEvent(
        event_type="reconciliation_match_rejected",
        source_type="reconciliation_match",
        source_id=match.id,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={"resolution_note": note},
        output_snapshot={"status": "rejected"},
    )
    db.add(audit)
    db.commit()

    return MatchActionResponse(
        id=match.id,
        status="rejected",
        resolved_at=match.updated_at,
        message="Reconciliation match rejected.",
    )
