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
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.schemas.reconciliation import (
    AdjustmentSuggestionRequest,
    AdjustmentSuggestionResponse,
    ManualMatchRequest,
    MatchActionRequest,
    MatchActionResponse,
    ReconcileRunRequest,
    ReconcileRunResponse,
    ReconciliationMatchListResponse,
    ReconciliationMatchResponse,
    ReconciliationSummaryResponse,
    SuggestedJournalLine,
)
from app.services.reconciliation import (
    execute_reconciliation_workflow,
    stream_reconciliation_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])
reconcile_router = APIRouter(prefix="/reconcile", tags=["Reconciliation"])


@router.get(
    "/stream/{bank_statement_import_id}",
    summary="Stream live reconciliation engine events via Server-Sent Events (SSE)",
)
@reconcile_router.get(
    "/stream/{bank_statement_import_id}",
    summary="Stream live reconciliation engine events via Server-Sent Events (SSE)",
)
def stream_reconciliation_engine(
    bank_statement_import_id: str,
) -> StreamingResponse:
    """Run reconciliation and stream real-time progress events via SSE."""
    return StreamingResponse(
        stream_reconciliation_workflow(bank_statement_import_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.post(
    "/suggest-adjustment",
    response_model=AdjustmentSuggestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask BookkeepingAgent to suggest a COA and adjusting journal entry for an unmatched bank transaction",
)
def suggest_adjustment_journal(
    req: AdjustmentSuggestionRequest,
    db: Session = Depends(get_db),
) -> AdjustmentSuggestionResponse:
    """Use BookkeepingAgent (LLM) to suggest Chart of Accounts classification and
    balanced double-entry journal lines for an unmatched bank transaction."""
    from app.agents.bookkeeping import run_bookkeeping_agent
    from app.models.coa import ChartOfAccount
    from app.models.reconciliation import BankTransaction

    tx = (
        db.query(BankTransaction)
        .filter(BankTransaction.id == req.bank_transaction_id)
        .first()
    )
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank transaction [{req.bank_transaction_id}] not found.",
        )

    # Load active Chart of Accounts
    coa_rows = (
        db.query(ChartOfAccount)
        .filter(ChartOfAccount.is_active == True)  # noqa: E712
        .order_by(ChartOfAccount.account_code)
        .all()
    )
    coa_list = [
        {
            "account_code": c.account_code,
            "account_name": c.account_name,
            "account_type": c.account_type,
            "normal_balance": c.normal_balance,
            "is_sensitive": c.is_sensitive,
            "description": c.description,
        }
        for c in coa_rows
    ]

    # Build extraction_data dict from bank transaction fields.
    # Bank statement amounts can be negative (debit/outflow) or positive (credit/inflow).
    # BookkeepingAgent requires total_amount > 0, so we pass abs() and encode the
    # direction semantically in extraction_notes for LLM reasoning.
    raw_amount = float(tx.amount)
    abs_amount = abs(raw_amount)
    tx_direction = "DEBIT (outflow / expense / payment)" if raw_amount < 0 else "CREDIT (inflow / revenue / receipt)"

    extraction_data = {
        "vendor_name": tx.description,
        "transaction_date": str(tx.transaction_date),
        "total_amount": abs_amount,
        "currency": tx.currency,
        "document_type": "bank_transaction",
        "line_items": [],
        "extraction_notes": (
            f"Unmatched bank statement mutation: '{tx.description}'. "
            f"Ref: {tx.reference_number or 'N/A'}. "
            f"Transaction direction: {tx_direction}. "
            f"Original signed amount: {raw_amount:,.2f} {tx.currency}. "
            "Please classify to the most appropriate account and generate a balanced journal entry."
        ),
    }

    logger.info(
        "Calling BookkeepingAgent for bank tx [%s]: %s",
        tx.id,
        tx.description,
    )

    agent_resp = run_bookkeeping_agent(
        extraction_data=extraction_data,
        chart_of_accounts=coa_list,
    )
    print("\n========================BOOKKEEPING AGENT RESPONSE========================\n", agent_resp)

    result = agent_resp.result
    suggested_lines = [
        SuggestedJournalLine(
            account_code=line.account_code,
            account_name=line.account_name,
            description=line.description,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
        )
        for line in result.journal_lines
    ]

    return AdjustmentSuggestionResponse(
        bank_transaction_id=str(tx.id),
        transaction_description=tx.description,
        transaction_date=str(tx.transaction_date),
        transaction_amount=float(tx.amount),
        currency=tx.currency,
        confidence_score=agent_resp.confidence_score,
        rationale=agent_resp.rationale,
        is_balanced=result.is_balanced,
        uses_sensitive_account=result.uses_sensitive_account,
        risk_flags=list(result.risk_flags or []),
        suggested_lines=suggested_lines,
        agent_name=agent_resp.agent_name,
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


@router.get(
    "/summary/{bank_statement_import_id}",
    response_model=ReconciliationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get reconciliation summary metrics for a bank statement import",
)
def get_reconciliation_summary(
    bank_statement_import_id: str,
    db: Session = Depends(get_db),
) -> ReconciliationSummaryResponse:
    """Compute and return balanced summary metrics deterministically."""
    try:
        imp_uuid = uuid.UUID(bank_statement_import_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bank_statement_import_id UUID format.",
        ) from None

    import_record = (
        db.query(BankStatementImport)
        .filter(BankStatementImport.id == imp_uuid)
        .first()
    )
    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank statement import [{bank_statement_import_id}] not found.",
        )

    transactions = (
        db.query(BankTransaction)
        .filter(BankTransaction.bank_statement_import_id == imp_uuid)
        .all()
    )

    matches = (
        db.query(ReconciliationMatch)
        .join(ReconciliationMatch.bank_transaction)
        .filter(BankTransaction.bank_statement_import_id == imp_uuid)
        .all()
    )

    posted_entries = (
        db.query(JournalEntry).filter(JournalEntry.status == "posted").all()
    )

    matched_je_ids = {
        m.journal_entry_id
        for m in matches
        if m.journal_entry_id and m.status in ("accepted", "matched")
    }

    # Deterministic Balances
    bank_balance = sum(float(t.amount) for t in transactions)

    # Calculate GL balance from posted entries matched to this statement
    gl_balance = 0.0
    for je in posted_entries:
        if je.id in matched_je_ids:
            tot_deb = sum(float(line.debit_amount) for line in je.lines)
            gl_balance += tot_deb

    diff = abs(bank_balance - gl_balance)
    is_balanced = diff < 0.01

    matched_count = sum(1 for m in matches if m.status in ("accepted", "matched"))
    proposed_count = sum(1 for m in matches if m.status == "proposed")
    unmatched_count = max(0, len(transactions) - (matched_count + proposed_count))
    gl_only_count = sum(1 for je in posted_entries if je.id not in matched_je_ids)

    # Calculate status & progress percentage
    total_tx = len(transactions)
    prog_pct = int((matched_count / total_tx * 100)) if total_tx > 0 else 0

    if is_balanced and matched_count == total_tx and total_tx > 0:
        recon_status = "reconciled"
    elif matched_count > 0:
        recon_status = "partially_reconciled"
    elif proposed_count > 0:
        recon_status = "review_required"
    else:
        recon_status = "unreconciled"

    sorted_dates = sorted(t.transaction_date for t in transactions)
    start_date = sorted_dates[0] if sorted_dates else None
    end_date = sorted_dates[-1] if sorted_dates else None

    return ReconciliationSummaryResponse(
        bank_statement_import_id=imp_uuid,
        statement_period_start=start_date,
        statement_period_end=end_date,
        bank_statement_balance=round(bank_balance, 2),
        gl_balance=round(gl_balance, 2),
        difference=round(diff, 2),
        is_balanced=is_balanced,
        status=recon_status,
        total_transactions=total_tx,
        matched_count=matched_count,
        proposed_count=proposed_count,
        unmatched_count=unmatched_count,
        gl_only_count=gl_only_count,
        progress_percentage=prog_pct,
    )


@router.post(
    "/manual-match",
    response_model=MatchActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually match a bank transaction with a general ledger journal entry",
)
def manual_match_transaction(
    req: ManualMatchRequest,
    db: Session = Depends(get_db),
) -> MatchActionResponse:
    """Manually link a bank transaction to a posted journal entry."""
    tx = (
        db.query(BankTransaction)
        .filter(BankTransaction.id == req.bank_transaction_id)
        .first()
    )
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank transaction [{req.bank_transaction_id}] not found.",
        )

    je = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == req.journal_entry_id)
        .first()
    )
    if not je:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry [{req.journal_entry_id}] not found.",
        )

    # Check if a match already exists for this transaction
    existing_match = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.bank_transaction_id == tx.id)
        .first()
    )

    if existing_match:
        existing_match.journal_entry_id = je.id
        existing_match.match_type = "manual"
        existing_match.status = "accepted"
        existing_match.confidence_score = 1.00
        existing_match.amount_score = 1.00
        existing_match.date_score = 1.00
        existing_match.vendor_score = 1.00
        existing_match.rationale = req.resolution_note or "Manually matched by user."
        existing_match.updated_at = datetime.now(UTC)
        match_record = existing_match
    else:
        match_record = ReconciliationMatch(
            id=uuid.uuid4(),
            bank_transaction_id=tx.id,
            journal_entry_id=je.id,
            match_type="manual",
            status="accepted",
            confidence_score=1.00,
            amount_score=1.00,
            date_score=1.00,
            vendor_score=1.00,
            rationale=req.resolution_note or "Manually matched by user.",
        )
        db.add(match_record)

    tx.status = "matched"

    audit = AuditEvent(
        event_type="reconciliation_match_manual",
        source_type="reconciliation_match",
        source_id=match_record.id,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={
            "bank_transaction_id": str(tx.id),
            "journal_entry_id": str(je.id),
            "note": req.resolution_note,
        },
        output_snapshot={"status": "accepted", "match_type": "manual"},
    )
    db.add(audit)
    db.commit()

    return MatchActionResponse(
        id=match_record.id,
        status="accepted",
        resolved_at=datetime.now(UTC),
        message="Manual reconciliation match created successfully.",
    )

