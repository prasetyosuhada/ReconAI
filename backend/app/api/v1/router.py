"""API v1 Main Router."""

from fastapi import APIRouter

from app.api.v1.audit import audit_log_router
from app.api.v1.audit import router as audit_events_router
from app.api.v1.bank import bank_router
from app.api.v1.bank import router as bank_statements_router
from app.api.v1.documents import router as documents_router
from app.api.v1.ledger import router as ledger_router
from app.api.v1.reconciliation import reconcile_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.review_items import router as review_items_router

api_v1_router = APIRouter()
api_v1_router.include_router(documents_router)
api_v1_router.include_router(review_items_router)
api_v1_router.include_router(ledger_router)
api_v1_router.include_router(bank_statements_router)
api_v1_router.include_router(bank_router)
api_v1_router.include_router(reconciliation_router)
api_v1_router.include_router(reconcile_router)
api_v1_router.include_router(audit_events_router)
api_v1_router.include_router(audit_log_router)
