"""API v1 Main Router."""

from fastapi import APIRouter

from app.api.v1.bank import bank_router
from app.api.v1.bank import router as bank_statements_router
from app.api.v1.documents import router as documents_router
from app.api.v1.ledger import router as ledger_router
from app.api.v1.review_items import router as review_items_router

api_v1_router = APIRouter()
api_v1_router.include_router(documents_router)
api_v1_router.include_router(review_items_router)
api_v1_router.include_router(ledger_router)
api_v1_router.include_router(bank_statements_router)
api_v1_router.include_router(bank_router)
