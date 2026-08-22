"""FastAPI Review Items API Router (Human-in-the-Loop Queue)."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.orchestrator import bookkeeping_node
from app.db.session import get_db
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.services.audit_service import log_event
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
from app.services.accounting import (
    post_journal_entry_to_ledger,
    save_journal_entry_safely,
)

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


def _parse_date_value(value: Any) -> date | None:
    """Parse dates from review payloads without trusting client formatting."""
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and len(value) >= 10:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _merge_review_payload(
    original_payload: dict[str, Any] | list[Any] | None,
    edited_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine agent payload and human corrections for downstream workflow."""
    payload = dict(original_payload) if isinstance(original_payload, dict) else {}
    payload.update(edited_payload or {})
    return payload


def _chart_of_accounts_payload(db: Session) -> list[dict[str, Any]]:
    coa_records = (
        db.query(ChartOfAccount).filter(ChartOfAccount.is_active.is_(True)).all()
    )
    return [
        {
            "account_code": coa.account_code,
            "account_name": coa.account_name,
            "account_type": coa.account_type,
            "normal_balance": coa.normal_balance,
            "is_sensitive": coa.is_sensitive,
            "description": coa.description,
        }
        for coa in coa_records
    ]


def _upsert_reviewed_extraction(
    doc: Document,
    payload: dict[str, Any],
    resolution_note: str | None,
    db: Session,
) -> DocumentExtraction:
    extraction = (
        db.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc.id)
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if not extraction:
        extraction = DocumentExtraction(id=uuid.uuid4(), document_id=doc.id)
        db.add(extraction)

    if payload.get("document_type"):
        doc.document_type = payload["document_type"]

    extraction.vendor_name = payload.get("vendor_name")
    extraction.transaction_date = _parse_date_value(payload.get("transaction_date"))
    extraction.subtotal_amount = payload.get("subtotal_amount")
    extraction.tax_amount = payload.get("tax_amount")
    extraction.total_amount = payload.get("total_amount")
    extraction.currency = payload.get("currency", "IDR")
    extraction.line_items = payload.get("line_items", [])
    extraction.raw_text = payload.get("raw_text")
    extraction.confidence_score = payload.get("confidence_score", 1.0)
    extraction.rationale = resolution_note or payload.get("rationale")
    extraction.status = "extracted"
    db.flush()
    return extraction


def _continue_document_to_bookkeeping(
    item: ReviewItem,
    payload: dict[str, Any],
    resolution_note: str | None,
    db: Session,
) -> str:
    """Continue a human-reviewed extraction directly into bookkeeping."""
    doc = db.query(Document).filter(Document.id == item.source_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document [{item.source_id}] not found.",
        )

    extraction = _upsert_reviewed_extraction(doc, payload, resolution_note, db)
    state = {
        "document_id": str(doc.id),
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "stored_file_path": doc.stored_file_path,
        "raw_text": extraction.raw_text,
        "extraction_id": str(extraction.id),
        "vendor_name": extraction.vendor_name,
        "transaction_date": extraction.transaction_date.isoformat()
        if extraction.transaction_date
        else None,
        "subtotal_amount": float(extraction.subtotal_amount)
        if extraction.subtotal_amount is not None
        else None,
        "tax_amount": float(extraction.tax_amount)
        if extraction.tax_amount is not None
        else None,
        "total_amount": float(extraction.total_amount)
        if extraction.total_amount is not None
        else None,
        "currency": extraction.currency,
        "document_type": doc.document_type,
        "line_items": extraction.line_items or [],
        "chart_of_accounts": _chart_of_accounts_payload(db),
        "status": "extracted",
        "needs_review": False,
        "risk_flags": [],
    }

    final_state = bookkeeping_node(state)
    proposed_journal = (
        final_state.get("journal_entry")
        or final_state.get("proposed_journal")
        or final_state.get("journal_lines")
    )

    # Pin AI output fields once — both JournalEntry and ReviewItem MUST reference
    # the exact same values to guarantee consistency across the GL and Review Queue modals.
    final_rationale: str | None = final_state.get("rationale")
    final_risk_flags: list[str] = final_state.get("risk_flags", []) or []
    final_confidence: float = float(final_state.get("confidence_score", 0.0))

    saved_journal_id = None
    journal_entry_date = _parse_date_value(final_state.get("entry_date")) or extraction.transaction_date or date.today()
    journal_desc = final_state.get("entry_description") or f"Journal for {doc.original_filename}"

    if proposed_journal:
        journal_data = {
            "document_id": doc.id,
            "extraction_id": extraction.id,
            "entry_date": journal_entry_date,
            "description": journal_desc,
            "status": "review_required" if final_state.get("needs_review") else "draft",
            "agent_name": "BookkeepingAgent",
            "confidence_score": final_confidence,
            "rationale": final_rationale,
            "risk_flags": final_risk_flags,
            "lines": proposed_journal,
        }
        save_res = save_journal_entry_safely(journal_data, db_session=db)
        if not save_res.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Journal save failed: {'; '.join(save_res.errors)}",
            )
        saved_journal_id = save_res.journal_entry_id

    needs_review = final_state.get("needs_review", False)
    next_status = final_state.get("status", "ready_to_post")

    if needs_review or next_status == "bookkeeping_review_required" or final_risk_flags:
        is_balanced = final_state.get("is_balanced", True)
        is_sensitive = "uses_sensitive_account" in final_risk_flags
        priority = "high" if is_sensitive or not is_balanced else "normal"

        # Lean, pinned payload — mirrors what is stored in the JournalEntry.
        review_payload: dict = {
            "journal_entry_id": str(saved_journal_id) if saved_journal_id else None,
            "vendor_name": extraction.vendor_name,
            "transaction_date": str(extraction.transaction_date or ""),
            "total_amount": float(extraction.total_amount) if extraction.total_amount is not None else None,
            "subtotal_amount": float(extraction.subtotal_amount) if extraction.subtotal_amount is not None else None,
            "tax_amount": float(extraction.tax_amount) if extraction.tax_amount is not None else None,
            "currency": extraction.currency,
            "line_items": extraction.line_items or [],
            "lines": proposed_journal,
            "entry_date": str(journal_entry_date),
            "description": journal_desc,
            # AI fields pinned from the same single agent run:
            "rationale": final_rationale,
            "risk_flags": final_risk_flags,
            "confidence_score": final_confidence,
            "is_balanced": is_balanced,
            "uses_sensitive_account": final_state.get("uses_sensitive_account", False),
        }

        source_id_val = (
            uuid.UUID(saved_journal_id)
            if isinstance(saved_journal_id, str)
            else (saved_journal_id if saved_journal_id else doc.id)
        )
        review_item = ReviewItem(
            id=uuid.uuid4(),
            review_type="bookkeeping",
            status="pending",
            priority=priority,
            source_type="journal_entry" if saved_journal_id else "document",
            source_id=source_id_val,
            title=f"Review Needed: {doc.original_filename}",
            summary=(
                "Bookkeeping agent flagged reviewed extraction. "
                f"Conf: {final_confidence:.2f}"
            ),
            suggested_action="Review the AI-generated journal entry account classification.",
            original_payload=review_payload,
        )
        db.add(review_item)

    doc.status = next_status

    decision_str = "Bookkeeping classified"
    if proposed_journal and isinstance(proposed_journal, list):
        debit_lines = [
            f"COA: {l.get('account_code')} - {l.get('account_name', '')}".strip(" -")
            for l in proposed_journal
            if float(l.get("debit_amount", 0.0) or 0.0) > 0
        ]
        if debit_lines:
            decision_str = debit_lines[0]

    reasoning_list = []
    if final_rationale:
        reasoning_list.append(final_rationale)
    for rf in final_risk_flags:
        reasoning_list.append(f"Risk flag: {rf}")

    log_event(
        db=db,
        event_type="bookkeeping_continued_after_extraction_review",
        source_type="document",
        source_id=doc.id,
        actor_type="agent",
        actor_name="BookkeepingAgent",
        input_snapshot={"review_item_id": str(item.id)},
        output_snapshot={
            "decision": decision_str,
            "reasoning": reasoning_list,
            "status": next_status,
            "journal_entry_id": str(saved_journal_id) if saved_journal_id else None,
            "needs_review": needs_review,
        },
        confidence_score=final_confidence,
        rationale=final_rationale,
        document_id=doc.id,
    )
    return next_status



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
    item = _get_review_item_or_404(review_item_id, db)

    payload: dict = {}
    if isinstance(item.original_payload, dict):
        payload = dict(item.original_payload)

    # Enrich with BankTransaction & ReconciliationMatch data if reconciliation item
    if item.source_type == "bank_transaction" and item.source_id:
        from app.models.reconciliation import BankTransaction, ReconciliationMatch

        tx = db.query(BankTransaction).filter(BankTransaction.id == item.source_id).first()
        if tx:
            payload.setdefault("tx_id", str(tx.id))
            payload.setdefault("transaction_date", str(tx.transaction_date))
            payload.setdefault("amount", float(tx.amount))
            payload.setdefault("description", tx.description)
            payload.setdefault("currency", tx.currency or "IDR")
            payload.setdefault("reference_number", tx.reference_number)

            # Check if match candidate exists
            match = (
                db.query(ReconciliationMatch)
                .filter(ReconciliationMatch.bank_transaction_id == tx.id)
                .order_by(ReconciliationMatch.created_at.desc())
                .first()
            )
            if match and match.journal_entry_id:
                payload.setdefault("proposed_journal_entry_id", str(match.journal_entry_id))
                payload.setdefault("confidence_score", match.confidence_score)
                payload.setdefault("amount_score", match.amount_score)
                payload.setdefault("date_score", match.date_score)
                payload.setdefault("vendor_score", match.vendor_score)
                if match.rationale:
                    payload.setdefault("rationale", match.rationale)

    return ReviewItemDetailResponse(
        id=item.id,
        review_type=item.review_type,
        status=item.status,
        priority=item.priority,
        source_type=item.source_type,
        source_id=item.source_id,
        title=item.title,
        summary=item.summary,
        suggested_action=item.suggested_action,
        original_payload=payload,
        edited_payload=item.edited_payload,
        resolution_note=item.resolution_note,
        resolved_by=item.resolved_by,
        resolved_at=item.resolved_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        # Convenience fields: populated from pinned payload for guaranteed consistency
        confidence_score=float(payload["confidence_score"])
        if "confidence_score" in payload and payload["confidence_score"] is not None
        else None,
        risk_flags=list(payload.get("risk_flags") or []),
        journal_entry_id=payload.get("journal_entry_id") or payload.get("proposed_journal_entry_id"),
    )



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
        if item.review_type == "extraction":
            payload = _merge_review_payload(item.original_payload)
            next_workflow_status = _continue_document_to_bookkeeping(
                item=item,
                payload=payload,
                resolution_note=resolution_note,
                db=db,
            )
        else:
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
                log_event(
                    db=db,
                    event_type="journal_entry_posted",
                    source_type="journal_entry",
                    source_id=je.id,
                    actor_type="human",
                    actor_name="human_user",
                    input_snapshot={"triggered_by": "review_item_approved"},
                    output_snapshot={
                        "status": "posted",
                        "journal_entry_id": str(je.id),
                        "gl_period": je.entry_date.strftime("%Y-%m") if je.entry_date else None,
                        "document_id": str(item.source_id),
                    },
                    rationale="Journal entry posted automatically after bookkeeping review approval.",
                    document_id=item.source_id,
                )
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
            _je_doc_id = getattr(je, "document_id", None)
            if _je_doc_id:
                doc = db.query(Document).filter(Document.id == _je_doc_id).first()
                if doc:
                    doc.status = "posted"
            log_event(
                db=db,
                event_type="journal_entry_posted",
                source_type="journal_entry",
                source_id=je.id,
                actor_type="human",
                actor_name="human_user",
                input_snapshot={"triggered_by": "review_item_approved"},
                output_snapshot={
                    "status": "posted",
                    "journal_entry_id": str(je.id),
                    "gl_period": je.entry_date.strftime("%Y-%m") if je.entry_date else None,
                    "document_id": str(_je_doc_id) if _je_doc_id else None,
                },
                rationale="Journal entry posted automatically after bookkeeping review approval.",
                document_id=_je_doc_id,
            )

    elif item.source_type == "bank_transaction":
        from app.models.reconciliation import BankTransaction, ReconciliationMatch

        tx = db.query(BankTransaction).filter(BankTransaction.id == item.source_id).first()
        match = (
            db.query(ReconciliationMatch)
            .filter(ReconciliationMatch.bank_transaction_id == item.source_id)
            .first()
        )
        if match:
            match.status = "accepted"
            match.updated_at = now_utc
            if tx:
                tx.status = "matched"
            next_workflow_status = "matched"
        elif tx:
            next_workflow_status = "approved"


    # Resolve document_id if available from source entity or payload
    doc_id_to_pass = None
    if item.source_type == "document":
        doc_id_to_pass = item.source_id
    elif item.source_type == "journal_entry":
        je_rec = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
        if je_rec and je_rec.document_id:
            doc_id_to_pass = je_rec.document_id

    # Audit Trail Event
    log_event(
        db=db,
        event_type="review_item_approved",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        human_action="approved",
        input_snapshot={"resolution_note": resolution_note, "review_type": item.review_type},
        output_snapshot={
            "status": "approved",
            "next_workflow_status": next_workflow_status,
        },
        document_id=doc_id_to_pass,
    )
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

    if item.source_type == "document" and item.review_type == "extraction":
        payload = _merge_review_payload(item.original_payload, req.edited_payload)
        next_workflow_status = _continue_document_to_bookkeeping(
            item=item,
            payload=payload,
            resolution_note=req.resolution_note,
            db=db,
        )

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
        _edit_je_doc_id = getattr(je, "document_id", None)
        if _edit_je_doc_id:
            doc = db.query(Document).filter(Document.id == _edit_je_doc_id).first()
            if doc:
                doc.status = "posted"
        log_event(
            db=db,
            event_type="journal_entry_posted",
            source_type="journal_entry",
            source_id=je.id,
            actor_type="human",
            actor_name="human_user",
            input_snapshot={"triggered_by": "review_item_edited"},
            output_snapshot={
                "status": "posted",
                "journal_entry_id": str(je.id),
                "gl_period": je.entry_date.strftime("%Y-%m") if je.entry_date else None,
                "document_id": str(_edit_je_doc_id) if _edit_je_doc_id else None,
            },
            rationale="Journal entry posted automatically after bookkeeping review edit and approval.",
            document_id=_edit_je_doc_id,
        )

    # Resolve document_id if available
    doc_id_to_pass = None
    if item.source_type == "document":
        doc_id_to_pass = item.source_id
    elif item.source_type == "journal_entry":
        je_rec = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
        if je_rec and je_rec.document_id:
            doc_id_to_pass = je_rec.document_id

    # Audit Event
    log_event(
        db=db,
        event_type="review_item_edited",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        human_action="edited",
        input_snapshot={
            "edited_payload": req.edited_payload,
            "resolution_note": req.resolution_note,
        },
        output_snapshot={
            "status": "edited",
            "next_workflow_status": next_workflow_status,
        },
        document_id=doc_id_to_pass,
    )
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

    elif item.source_type == "bank_transaction":
        from app.models.adjustment_suggestion import AdjustmentSuggestion
        from app.models.reconciliation import BankTransaction, ReconciliationMatch
        from app.services.reconciliation import compute_and_save_adjustment_suggestion

        tx = db.query(BankTransaction).filter(BankTransaction.id == item.source_id).first()
        match = (
            db.query(ReconciliationMatch)
            .filter(ReconciliationMatch.bank_transaction_id == item.source_id)
            .first()
        )
        if match:
            match.status = "rejected"
            match.updated_at = now_utc
        if tx:
            tx.status = "imported"
            existing_sug = (
                db.query(AdjustmentSuggestion)
                .filter(AdjustmentSuggestion.bank_transaction_id == tx.id)
                .first()
            )
            if not existing_sug:
                try:
                    compute_and_save_adjustment_suggestion(tx=tx, db=db)
                except Exception as e:
                    logger.warning("Could not generate eager suggestion on review item reject: %s", e)



    # Resolve document_id if available
    doc_id_to_pass = None
    if item.source_type == "document":
        doc_id_to_pass = item.source_id
    elif item.source_type == "journal_entry":
        je_rec = db.query(JournalEntry).filter(JournalEntry.id == item.source_id).first()
        if je_rec and je_rec.document_id:
            doc_id_to_pass = je_rec.document_id

    # Audit Event
    log_event(
        db=db,
        event_type="review_item_rejected",
        source_type="review_item",
        source_id=item.id,
        actor_type="human",
        actor_name="human_user",
        human_action="rejected",
        input_snapshot={"resolution_note": resolution_note, "review_type": item.review_type},
        output_snapshot={"status": "rejected"},
        document_id=doc_id_to_pass,
    )
    db.commit()

    return ReviewRejectResponse(
        id=item.id,
        status="rejected",
        resolved_at=now_utc,
        message="Review item rejected.",
    )
