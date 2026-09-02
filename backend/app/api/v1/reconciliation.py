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
from app.models.adjustment_suggestion import AdjustmentSuggestion
from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)
from app.models.review import ReviewItem
from app.schemas.reconciliation import (
    AdjustmentSuggestionRequest,
    AdjustmentSuggestionResponse,
    CreateAdjustmentJournalRequest,
    CreateAdjustmentJournalResponse,
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
from app.services.accounting import save_journal_entry_safely
from app.services.audit_service import log_event
from app.services.reconciliation import (
    compute_and_save_adjustment_suggestion,
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
    summary=(
        "Retrieve pre-computed BookkeepingAgent COA suggestion for an unmatched "
        "bank transaction"
    ),
)
def suggest_adjustment_journal(
    req: AdjustmentSuggestionRequest,
    db: Session = Depends(get_db),
) -> AdjustmentSuggestionResponse:
    """Read the BookkeepingAgent suggestion stored in DB during Run Recon Engine.

    Suggestions are generated eagerly for Bank Only transactions when the
    reconciliation workflow runs. This endpoint is a fast DB read — no LLM is invoked.
    Returns 404 if Run Recon Engine has not yet been executed for this transaction.
    """
    from app.models.adjustment_suggestion import AdjustmentSuggestion
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

    suggestion = (
        db.query(AdjustmentSuggestion)
        .filter(AdjustmentSuggestion.bank_transaction_id == tx.id)
        .first()
    )
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No COA suggestion found for bank transaction "
                f"[{req.bank_transaction_id}]. "
                "Suggestion is generated automatically when the match is rejected "
                "or unmatched. "
                "Run 'Run Recon Engine' first if this is a Bank Only transaction."
            ),
        )

    logger.info("Returning stored BookkeepingAgent suggestion for bank tx [%s]", tx.id)

    return AdjustmentSuggestionResponse(
        bank_transaction_id=str(tx.id),
        transaction_description=tx.description,
        transaction_date=str(tx.transaction_date),
        transaction_amount=float(tx.amount),
        currency=tx.currency,
        confidence_score=float(suggestion.confidence_score),
        rationale=suggestion.rationale,
        is_balanced=suggestion.is_balanced,
        uses_sensitive_account=suggestion.uses_sensitive_account,
        risk_flags=list(suggestion.risk_flags or []),
        suggested_lines=[
            SuggestedJournalLine(
                account_code=line["account_code"],
                account_name=line["account_name"],
                description=line.get("description"),
                debit_amount=line.get("debit_amount", 0.0),
                credit_amount=line.get("credit_amount", 0.0),
            )
            for line in (suggestion.suggested_lines or [])
        ],
        agent_name=suggestion.agent_name,
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

    if match.bank_transaction_id:
        rev_item = (
            db.query(ReviewItem)
            .filter(
                ReviewItem.source_type == "bank_transaction",
                ReviewItem.source_id == match.bank_transaction_id,
                ReviewItem.status == "pending",
            )
            .first()
        )
        if rev_item:
            rev_item.status = "approved"
            rev_item.resolved_by = "human_user"
            rev_item.resolved_at = datetime.now(UTC)
            rev_item.resolution_note = (
                action_req.resolution_note
                if action_req
                else "Approved in Reconciliation View."
            )

    note = action_req.resolution_note if action_req else None
    matched_je_rec = (
        db.query(JournalEntry).filter(JournalEntry.id == match.journal_entry_id).first()
        if match.journal_entry_id
        else None
    )
    doc_id_to_pass = matched_je_rec.document_id if matched_je_rec else None

    log_event(
        db=db,
        event_type="reconciliation_match_accepted",
        source_type="reconciliation_match",
        source_id=match.id,
        actor_type="human",
        actor_name="api_user",
        human_action="accepted",
        input_snapshot={"resolution_note": note},
        output_snapshot={"status": "accepted"},
        document_id=doc_id_to_pass,
    )
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

    if match.bank_transaction_id:
        rev_item = (
            db.query(ReviewItem)
            .filter(
                ReviewItem.source_type == "bank_transaction",
                ReviewItem.source_id == match.bank_transaction_id,
                ReviewItem.status == "pending",
            )
            .first()
        )
        if rev_item:
            rev_item.status = "rejected"
            rev_item.resolved_by = "human_user"
            rev_item.resolved_at = datetime.now(UTC)
            rev_item.resolution_note = (
                action_req.resolution_note
                if action_req
                else "Rejected in Reconciliation View."
            )

    # Eagerly compute & save COA suggestion for newly unmatched transaction
    if match.bank_transaction:
        existing_sug = (
            db.query(AdjustmentSuggestion)
            .filter(
                AdjustmentSuggestion.bank_transaction_id == match.bank_transaction.id
            )
            .first()
        )
        if not existing_sug:
            try:
                compute_and_save_adjustment_suggestion(tx=match.bank_transaction, db=db)
            except Exception as e:
                logger.warning(
                    "Could not generate eager suggestion on match reject for "
                    "tx [%s]: %s",
                    match.bank_transaction_id,
                    e,
                )

    note = action_req.resolution_note if action_req else None
    matched_je_rec = (
        db.query(JournalEntry).filter(JournalEntry.id == match.journal_entry_id).first()
        if match.journal_entry_id
        else None
    )
    doc_id_to_pass = matched_je_rec.document_id if matched_je_rec else None

    log_event(
        db=db,
        event_type="reconciliation_match_rejected",
        source_type="reconciliation_match",
        source_id=match.id,
        actor_type="human",
        actor_name="api_user",
        human_action="rejected",
        input_snapshot={"resolution_note": note},
        output_snapshot={"status": "rejected"},
        document_id=doc_id_to_pass,
    )
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
        db.query(BankStatementImport).filter(BankStatementImport.id == imp_uuid).first()
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
    prog_pct = int(matched_count / total_tx * 100) if total_tx > 0 else 0

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

    je = db.query(JournalEntry).filter(JournalEntry.id == req.journal_entry_id).first()
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

    doc_id_to_pass = je.document_id if je else None

    log_event(
        db=db,
        event_type="reconciliation_match_manual",
        source_type="reconciliation_match",
        source_id=match_record.id,
        actor_type="human",
        actor_name="api_user",
        human_action="manual_match",
        input_snapshot={
            "bank_transaction_id": str(tx.id),
            "journal_entry_id": str(je.id),
            "note": req.resolution_note,
        },
        output_snapshot={"status": "accepted", "match_type": "manual"},
        document_id=doc_id_to_pass,
    )
    db.commit()

    return MatchActionResponse(
        id=match_record.id,
        status="accepted",
        resolved_at=datetime.now(UTC),
        message="Manual reconciliation match created successfully.",
    )


@router.post(
    "/create-adjustment",
    response_model=CreateAdjustmentJournalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and post adjusting journal entry from an unmatched bank mutation",
)
def create_and_post_adjustment_entry(
    req: CreateAdjustmentJournalRequest,
    db: Session = Depends(get_db),
) -> CreateAdjustmentJournalResponse:
    """Create a balanced double-entry journal entry for an unmatched bank mutation,

    post it to the General Ledger, and mark the transaction as reconciled.
    """
    from app.models.adjustment_suggestion import AdjustmentSuggestion
    from app.models.review import ReviewItem

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

    # 1. Determine double-entry lines
    if req.lines and len(req.lines) >= 2:
        lines_data = [
            {
                "account_code": line.account_code,
                "account_name": line.account_name,
                "description": line.description,
                "debit_amount": line.debit_amount,
                "credit_amount": line.credit_amount,
            }
            for line in req.lines
        ]
    else:
        # Fallback to stored suggestion
        suggestion = (
            db.query(AdjustmentSuggestion)
            .filter(AdjustmentSuggestion.bank_transaction_id == tx.id)
            .first()
        )
        if suggestion and suggestion.suggested_lines:
            lines_data = suggestion.suggested_lines
        else:
            raw_amt = float(tx.amount)
            abs_amt = abs(raw_amt)
            if raw_amt < 0:
                lines_data = [
                    {
                        "account_code": "5900",
                        "account_name": "Miscellaneous Expense",
                        "description": tx.description,
                        "debit_amount": abs_amt,
                        "credit_amount": 0.0,
                    },
                    {
                        "account_code": "1010",
                        "account_name": "Bank Account",
                        "description": "Bank Outflow",
                        "debit_amount": 0.0,
                        "credit_amount": abs_amt,
                    },
                ]
            else:
                lines_data = [
                    {
                        "account_code": "1010",
                        "account_name": "Bank Account",
                        "description": "Bank Inflow",
                        "debit_amount": abs_amt,
                        "credit_amount": 0.0,
                    },
                    {
                        "account_code": "4000",
                        "account_name": "Sales Revenue",
                        "description": tx.description,
                        "debit_amount": 0.0,
                        "credit_amount": abs_amt,
                    },
                ]

    entry_date = req.entry_date or tx.transaction_date
    entry_desc = req.description or f"Adjustment: {tx.description}"

    # 2. Persist journal entry safely with deterministic double-entry guardrail
    journal_payload = {
        "entry_date": entry_date,
        "description": entry_desc,
        "status": "posted",
        "source_type": "reconciliation",
        "agent_name": "BookkeepingAgent",
        "confidence_score": 1.0,
        "rationale": (
            f"Adjusting journal entry created from bank mutation: {tx.description}"
        ),
        "lines": lines_data,
    }

    save_result = save_journal_entry_safely(
        journal_data=journal_payload,
        db_session=db,
        raise_on_error=False,
    )

    if not save_result.success or not save_result.journal_entry_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Failed to post adjusting journal entry: "
                f"{'; '.join(save_result.errors)}"
            ),
        )

    je_id = uuid.UUID(save_result.journal_entry_id)
    je = db.query(JournalEntry).filter(JournalEntry.id == je_id).first()
    if je:
        je.posted_at = datetime.now(UTC)

    # 3. Update Bank Transaction status
    tx.status = "matched"

    # 4. Upsert ReconciliationMatch record
    existing_match = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.bank_transaction_id == tx.id)
        .first()
    )

    if existing_match:
        existing_match.journal_entry_id = je_id
        existing_match.match_type = "adjustment"
        existing_match.status = "accepted"
        existing_match.confidence_score = 1.00
        existing_match.amount_score = 1.00
        existing_match.date_score = 1.00
        existing_match.vendor_score = 1.00
        existing_match.rationale = (
            "Adjusting journal entry created and posted to ledger."
        )
        existing_match.updated_at = datetime.now(UTC)
        match_rec = existing_match
    else:
        match_rec = ReconciliationMatch(
            id=uuid.uuid4(),
            bank_transaction_id=tx.id,
            journal_entry_id=je_id,
            match_type="adjustment",
            status="accepted",
            confidence_score=1.00,
            amount_score=1.00,
            date_score=1.00,
            vendor_score=1.00,
            rationale="Adjusting journal entry created and posted to ledger.",
        )
        db.add(match_rec)

    # 5. Resolve any pending ReviewItem for this bank transaction
    pending_reviews = (
        db.query(ReviewItem)
        .filter(
            ReviewItem.source_type == "bank_transaction",
            ReviewItem.source_id == tx.id,
            ReviewItem.status == "pending",
        )
        .all()
    )
    for r in pending_reviews:
        r.status = "approved"
        r.resolution_action = "created_adjustment_entry"
        r.resolved_at = datetime.now(UTC)

    # 6. Audit Trail
    log_event(
        db=db,
        event_type="reconciliation_adjustment_created",
        source_type="journal_entry",
        source_id=je_id,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={
            "bank_transaction_id": str(tx.id),
            "lines": lines_data,
        },
        output_snapshot={
            "journal_entry_id": str(je_id),
            "reconciliation_match_id": str(match_rec.id),
            "status": "posted",
        },
    )
    db.commit()

    total_deb = sum(float(line.get("debit_amount", 0.0)) for line in lines_data)
    total_cred = sum(float(line.get("credit_amount", 0.0)) for line in lines_data)

    return CreateAdjustmentJournalResponse(
        journal_entry_id=je_id,
        bank_transaction_id=tx.id,
        reconciliation_match_id=match_rec.id,
        status="posted",
        total_debit=total_deb,
        total_credit=total_cred,
        message=(
            "Adjusting journal entry created and posted to General Ledger successfully."
        ),
    )
