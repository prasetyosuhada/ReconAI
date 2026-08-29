"""FastAPI Ledger API Router (General Ledger & Trial Balance)."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.coa import ChartOfAccount
from app.models.document import Document
from app.models.journal import JournalEntry, JournalEntryLine
from app.schemas.ledger import (
    ChartOfAccountListResponse,
    JournalEntryDetailResponse,
    JournalEntryListItemResponse,
    JournalEntryListResponse,
    JournalLineResponse,
    PostJournalEntryResponse,
    TrialBalanceAccountBalance,
    TrialBalanceResponse,
)
from app.services.accounting import post_journal_entry_to_ledger
from app.services.audit_service import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ledger", tags=["Ledger"])


def _to_journal_list_item(entry: JournalEntry) -> JournalEntryListItemResponse:
    """Helper to convert JournalEntry ORM object to JournalEntryListItemResponse."""
    tot_debit = sum(float(line.debit_amount) for line in entry.lines)
    tot_credit = sum(float(line.credit_amount) for line in entry.lines)

    return JournalEntryListItemResponse(
        id=entry.id,
        document_id=entry.document_id,
        extraction_id=entry.extraction_id,
        entry_date=entry.entry_date,
        description=entry.description,
        status=entry.status,
        agent_name=entry.agent_name,
        confidence_score=entry.confidence_score,
        total_debit=tot_debit,
        total_credit=tot_credit,
        posted_at=entry.posted_at,
        created_at=entry.created_at,
    )


def _to_journal_detail(entry: JournalEntry) -> JournalEntryDetailResponse:
    """Helper to convert JournalEntry ORM object to JournalEntryDetailResponse."""
    line_responses = []
    tot_debit = 0.0
    tot_credit = 0.0
    for line in entry.lines:
        ac_code = line.account.account_code if line.account else "UNKNOWN"
        ac_name = line.account.account_name if line.account else "Unassigned"
        deb = float(line.debit_amount)
        cred = float(line.credit_amount)
        tot_debit += deb
        tot_credit += cred
        line_responses.append(
            JournalLineResponse(
                id=line.id,
                line_number=line.line_number,
                account_id=line.account_id,
                account_code=ac_code,
                account_name=ac_name,
                debit_amount=deb,
                credit_amount=cred,
                description=line.description,
            )
        )

    return JournalEntryDetailResponse(
        id=entry.id,
        document_id=entry.document_id,
        extraction_id=entry.extraction_id,
        entry_date=entry.entry_date,
        description=entry.description,
        status=entry.status,
        agent_name=entry.agent_name,
        confidence_score=entry.confidence_score,
        rationale=entry.rationale,
        risk_flags=entry.risk_flags,
        total_debit=tot_debit,
        total_credit=tot_credit,
        lines=line_responses,
        posted_at=entry.posted_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get(
    "",
    response_model=JournalEntryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List journal entries in General Ledger",
)
@router.get(
    "/journal-entries",
    response_model=JournalEntryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List journal entries",
    include_in_schema=False,
)
def list_journal_entries(
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by status e.g. draft, review_required, approved, posted",
    ),
    document_id: str | None = Query(None, description="Filter by source document UUID"),
    search: str | None = Query(
        None,
        description=(
            "Search description, entry date, #JE-ID, or linked document filename"
        ),
    ),
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> JournalEntryListResponse:
    """Fetch paginated journal entries from the general ledger with optional search."""
    query = db.query(JournalEntry).outerjoin(
        Document, JournalEntry.document_id == Document.id
    )

    if status_filter:
        query = query.filter(JournalEntry.status == status_filter)

    if document_id:
        try:
            doc_uuid = uuid.UUID(document_id)
            query = query.filter(JournalEntry.document_id == doc_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid document UUID format.",
            ) from None

    if search and search.strip():
        s_clean = search.strip()
        term = f"%{s_clean}%"
        search_conds = [
            JournalEntry.description.ilike(term),
            Document.original_filename.ilike(term),
        ]
        # Match JE ID or prefix like #JE-1234abcd
        id_part = (
            s_clean.replace("#JE-", "").replace("JE-", "").replace("#", "").strip()
        )
        if id_part:
            search_conds.append(cast(JournalEntry.id, String).ilike(f"%{id_part}%"))

        # Try parsing as date
        for d_fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed_d = datetime.strptime(s_clean, d_fmt).date()
                search_conds.append(JournalEntry.entry_date == parsed_d)
                break
            except ValueError:
                pass

        query = query.filter(or_(*search_conds))

    total_count = query.with_entities(func.count(JournalEntry.id)).scalar() or 0

    entries = (
        query.order_by(JournalEntry.created_at.desc()).offset(offset).limit(limit).all()
    )

    items = [_to_journal_list_item(e) for e in entries]

    return JournalEntryListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/journal-entries/{journal_entry_id}",
    response_model=JournalEntryDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single journal entry with line items",
)
def get_journal_entry_detail(
    journal_entry_id: str,
    db: Session = Depends(get_db),
) -> JournalEntryDetailResponse:
    """Fetch journal entry details by UUID."""
    try:
        je_uuid = uuid.UUID(journal_entry_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid journal entry UUID format.",
        ) from None

    entry = db.query(JournalEntry).filter(JournalEntry.id == je_uuid).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry [{journal_entry_id}] not found.",
        )

    return _to_journal_detail(entry)


@router.post(
    "/journal-entries/{journal_entry_id}/post",
    response_model=PostJournalEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Post approved journal entry to general ledger",
)
def post_journal_entry(
    journal_entry_id: str,
    db: Session = Depends(get_db),
) -> PostJournalEntryResponse:
    """Post an approved or ready_to_post journal entry to ledger."""
    try:
        je_uuid = uuid.UUID(journal_entry_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid journal entry UUID format.",
        ) from None

    entry = db.query(JournalEntry).filter(JournalEntry.id == je_uuid).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry [{journal_entry_id}] not found.",
        )

    post_res = post_journal_entry_to_ledger(
        journal_entry=entry, db_session=db, posted_by="api_user"
    )
    if not post_res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Posting failed: {'; '.join(post_res.errors)}",
        )

    posted_at_dt = (
        datetime.fromisoformat(post_res.posted_at)
        if post_res.posted_at
        else datetime.now(UTC)
    )

    if entry.document_id:
        doc = db.query(Document).filter(Document.id == entry.document_id).first()
        if doc:
            doc.status = "posted"

    log_event(
        db=db,
        event_type="journal_entry_posted",
        source_type="journal_entry",
        source_id=entry.id,
        actor_type="human",
        actor_name="api_user",
        input_snapshot={"journal_entry_id": str(entry.id)},
        output_snapshot={
            "status": "posted",
            "journal_entry_id": str(entry.id),
            "gl_period": entry.entry_date.strftime("%Y-%m")
            if entry.entry_date
            else None,
            "document_id": str(entry.document_id) if entry.document_id else None,
        },
        rationale="Journal entry posted to general ledger.",
        document_id=entry.document_id,
    )
    db.commit()

    return PostJournalEntryResponse(
        id=entry.id,
        status="posted",
        posted_at=posted_at_dt,
        trial_balance_status="balanced",
    )


@router.get(
    "/chart-of-accounts",
    response_model=ChartOfAccountListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Chart of Accounts",
)
def list_chart_of_accounts(
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> ChartOfAccountListResponse:
    """Fetch paginated Chart of Accounts."""
    query = db.query(ChartOfAccount).filter(ChartOfAccount.is_active.is_(True))
    total_count = query.with_entities(func.count(ChartOfAccount.id)).scalar() or 0

    accounts = (
        query.order_by(ChartOfAccount.account_code.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return ChartOfAccountListResponse(
        items=accounts,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/trial-balance",
    response_model=TrialBalanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Trial Balance validation report across posted journal entries",
)
def get_trial_balance(
    as_of: str | None = Query(
        None, alias="as_of_date", description="Target cutoff date (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db),
) -> TrialBalanceResponse:
    """Generate Trial Balance report for all posted journal entries."""
    query = (
        db.query(JournalEntryLine)
        .join(JournalEntry)
        .filter(JournalEntry.status == "posted")
    )

    cutoff_date = date.today()
    if as_of:
        try:
            cutoff_date = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
            query = query.filter(JournalEntry.entry_date <= cutoff_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format for as_of_date. Use YYYY-MM-DD.",
            ) from None

    posted_lines = query.all()

    # Aggregate by account
    account_totals: dict[str, dict[str, Any]] = {}
    total_debits = 0.0
    total_credits = 0.0

    for line in posted_lines:
        ac_code = line.account.account_code if line.account else "UNKNOWN"
        ac_name = line.account.account_name if line.account else "Unassigned"
        ac_type = line.account.account_type if line.account else "expense"

        if ac_code not in account_totals:
            account_totals[ac_code] = {
                "account_code": ac_code,
                "account_name": ac_name,
                "account_type": ac_type,
                "debit_balance": 0.0,
                "credit_balance": 0.0,
            }

        deb = float(line.debit_amount)
        cred = float(line.credit_amount)

        account_totals[ac_code]["debit_balance"] += deb
        account_totals[ac_code]["credit_balance"] += cred

        total_debits += deb
        total_credits += cred

    diff = abs(total_debits - total_credits)
    tb_status = "balanced" if diff < 0.01 else "unbalanced"

    accounts_list = [
        TrialBalanceAccountBalance(
            account_code=v["account_code"],
            account_name=v["account_name"],
            account_type=v["account_type"],
            debit_balance=round(v["debit_balance"], 2),
            credit_balance=round(v["credit_balance"], 2),
        )
        for v in sorted(account_totals.values(), key=lambda x: x["account_code"])
    ]

    return TrialBalanceResponse(
        as_of_date=cutoff_date,
        status=tb_status,
        total_debits=round(total_debits, 2),
        total_credits=round(total_credits, 2),
        difference=round(diff, 2),
        accounts=accounts_list,
    )
