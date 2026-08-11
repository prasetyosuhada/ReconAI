"""FastAPI Review Items API Router (Human-in-the-Loop Queue)."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.schemas.review import (
    ReviewApproveRequest,
    ReviewApproveResponse,
    ReviewEditRequest,
    ReviewEditResponse,
    ReviewItemDetailResponse,
    ReviewItemListResponse,
    ReviewRejectRequest,
    ReviewRejectResponse,
)
from app.services.accounting import post_journal_entry_to_ledger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review-items", tags=["Review Items"])


def _get_review_item_or_404(review_item_id: str, db: Session) -> ReviewItem:
    """Helper to parse UUID and query review item."""
    try:
        item_uuid = uuid.UUID(review_item_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review item UUID format.",
        ) from None

    item = db.query(ReviewItem).filter(ReviewItem.id == item_uuid).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review item [{review_item_id}] not found.",
        )
    return item


@router.get(
    "",
    response_model=ReviewItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Human-in-the-Loop review queue items",
)
def list_review_items(
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by status e.g. pending, approved, edited, rejected",
    ),
    review_type: str | None = Query(
        None,
        description="Filter by type e.g. extraction, bookkeeping, reconciliation",
    ),
    limit: int = Query(50, ge=1, le=250, description="Pagination limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> ReviewItemListResponse:
    """Fetch paginated Human-in-the-Loop review items with optional filters."""
    query = db.query(ReviewItem)

    if status_filter:
        query = query.filter(ReviewItem.status == status_filter)

    if review_type:
        query = query.filter(ReviewItem.review_type == review_type)

    total_count = query.with_entities(func.count(ReviewItem.id)).scalar() or 0

    items = (
        query.order_by(ReviewItem.created_at.desc()).offset(offset).limit(limit).all()
    )

    return ReviewItemListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{review_item_id}",
    response_model=ReviewItemDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single review item details with full original & edited payloads",
)
def get_review_item_detail(
    review_item_id: str,
    db: Session = Depends(get_db),
) -> ReviewItemDetailResponse:
    """Fetch review item details by UUID."""
    return _get_review_item_or_404(review_item_id, db)


@router.post(
    "/{review_item_id}/approve",
    response_model=ReviewApproveResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve review item as-is and advance workflow",
)
def approve_review_item(
    review_item_id: str,
    req: ReviewApproveRequest | None = None,
    db: Session = Depends(get_db),
) -> ReviewApproveResponse:
    """Approve a pending review item as-is."""
    item = _get_review_item_or_404(review_item_id, db)

    if item.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Review item [{review_item_id}] is already {item.status}.",
        )

    now_utc = datetime.now(UTC)
    resolution_note = req.resolution_note if req else None

    item.status = "approved"
    item.resolution_note = resolution_note
    item.resolved_by = "human_user"
    item.resolved_at = now_utc

    next_workflow_status = "approved"

    # Advance workflow based on source entity
    if item.source_type == "document":
        doc = db.query(Document).filter(Document.id == item.source_id).first()
        je = (
            db.query(JournalEntry)
            .filter(JournalEntry.document_id == item.source_id)
            .first()
        )

        if je:
            post_res = post_journal_entry_to_ledger(
                journal_entry=je, db_session=db, posted_by="human_user"
            )
            if not post_res.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Posting failed: {'; '.join(post_res.errors)}",
                )
            next_workflow_status = "posted"
            if doc:
                doc.status = "posted"
        elif doc:
            doc.status = "approved"
            next_workflow_status = "approved"

    elif item.source_type == "journal_entry":
        je = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
        if je:
            post_res = post_journal_entry_to_ledger(
                journal_entry=je, db_session=db, posted_by="human_user"
            )
            if not post_res.success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Posting failed: {'; '.join(post_res.errors)}",
                )
            next_workflow_status = "posted"

    # Audit Trail Event
    audit = AuditEvent(
        event_type="review_item_approved",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        input_snapshot={"resolution_note": resolution_note},
        output_snapshot={
            "status": "approved",
            "next_workflow_status": next_workflow_status,
        },
    )
    db.add(audit)
    db.commit()

    return ReviewApproveResponse(
        id=item.id,
        status="approved",
        resolved_at=now_utc,
        next_workflow_status=next_workflow_status,
        message="Review item approved successfully.",
    )


@router.post(
    "/{review_item_id}/edit",
    response_model=ReviewEditResponse,
    status_code=status.HTTP_200_OK,
    summary="Edit payload parameters of review item and approve",
)
def edit_review_item(
    review_item_id: str,
    req: ReviewEditRequest,
    db: Session = Depends(get_db),
) -> ReviewEditResponse:
    """Edit review item payload parameters and approve."""
    item = _get_review_item_or_404(review_item_id, db)

    if item.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Review item [{review_item_id}] is already {item.status}.",
        )

    now_utc = datetime.now(UTC)
    item.status = "edited"
    item.edited_payload = req.edited_payload
    item.resolution_note = req.resolution_note
    item.resolved_by = "human_user"
    item.resolved_at = now_utc

    next_workflow_status = "edited"

    # If editing journal lines in payload, update JournalEntry model
    je = None
    if item.source_type == "journal_entry":
        je = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
    elif item.source_type == "document":
        je = (
            db.query(JournalEntry)
            .filter(JournalEntry.document_id == item.source_id)
            .first()
        )

    if je and "lines" in req.edited_payload:
        # Clear existing lines and replace with edited lines
        db.query(JournalEntryLine).filter(
            JournalEntryLine.journal_entry_id == je.id
        ).delete()

        new_lines = req.edited_payload.get("lines", [])
        for line_idx, line in enumerate(new_lines, start=1):
            ac_code = str(line.get("account_code", ""))
            ac_name = str(line.get("account_name", "Unassigned Account"))
            deb = float(line.get("debit_amount", 0.0))
            cred = float(line.get("credit_amount", 0.0))
            l_desc = line.get("description")

            coa_record = None
            if ac_code:
                coa_record = (
                    db.query(ChartOfAccount)
                    .filter(ChartOfAccount.account_code == ac_code)
                    .first()
                )

            if not coa_record:
                is_sens = ac_code in ("1000", "1010", "2100", "3000", "9999")
                coa_record = ChartOfAccount(
                    id=uuid.uuid4(),
                    account_code=ac_code or f"AUTO_{uuid.uuid4().hex[:6]}",
                    account_name=ac_name or "Auto Generated Account",
                    account_type="expense" if deb > 0 else "liability",
                    normal_balance="debit" if deb > 0 else "credit",
                    is_sensitive=is_sens,
                )
                db.add(coa_record)
                db.flush()

            orm_line = JournalEntryLine(
                line_number=line_idx,
                account_id=coa_record.id,
                debit_amount=deb,
                credit_amount=cred,
                description=l_desc,
            )
            je.lines.append(orm_line)

        # Attempt to post updated journal entry to ledger
        post_res = post_journal_entry_to_ledger(
            journal_entry=je, db_session=db, posted_by="human_user"
        )
        if not post_res.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Posting failed: {'; '.join(post_res.errors)}",
            )
        next_workflow_status = "posted"

    # Audit Event
    audit = AuditEvent(
        event_type="review_item_edited",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        input_snapshot={
            "edited_payload": req.edited_payload,
            "resolution_note": req.resolution_note,
        },
        output_snapshot={
            "status": "edited",
            "next_workflow_status": next_workflow_status,
        },
    )
    db.add(audit)
    db.commit()

    return ReviewEditResponse(
        id=item.id,
        status="edited",
        resolved_at=now_utc,
        next_workflow_status=next_workflow_status,
        message="Review item edited and approved.",
    )


@router.post(
    "/{review_item_id}/reject",
    response_model=ReviewRejectResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject review item and mark source entity rejected",
)
def reject_review_item(
    review_item_id: str,
    req: ReviewRejectRequest | None = None,
    db: Session = Depends(get_db),
) -> ReviewRejectResponse:
    """Reject a pending review item."""
    item = _get_review_item_or_404(review_item_id, db)

    if item.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Review item [{review_item_id}] is already {item.status}.",
        )

    now_utc = datetime.now(UTC)
    resolution_note = req.resolution_note if req else None

    item.status = "rejected"
    item.resolution_note = resolution_note
    item.resolved_by = "human_user"
    item.resolved_at = now_utc

    # Update source entity status
    if item.source_type == "document":
        doc = db.query(Document).filter(Document.id == item.source_id).first()
        if doc:
            doc.status = "rejected"
        je = (
            db.query(JournalEntry)
            .filter(JournalEntry.document_id == item.source_id)
            .first()
        )
        if je:
            je.status = "rejected"

    elif item.source_type == "journal_entry":
        je = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
        if je:
            je.status = "rejected"

    # Audit Event
    audit = AuditEvent(
        event_type="review_item_rejected",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        input_snapshot={"resolution_note": resolution_note},
        output_snapshot={"status": "rejected"},
    )
    db.add(audit)
    db.commit()

    return ReviewRejectResponse(
        id=item.id,
        status="rejected",
        resolved_at=now_utc,
        message="Review item rejected.",
    )
