"""FastAPI Review Items API Router (Human-in-the-Loop Queue)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.review import ReviewItem
from app.schemas.review import (
    ReviewItemDetailResponse,
    ReviewItemListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review-items", tags=["Review Items"])


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
