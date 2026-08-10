"""Orchestrator Routing Logic and LangGraph Nodes for ReconAI.

Provides deterministic conditional routing functions and LangGraph workflow nodes
to enforce confidence thresholds (confidence < 0.85 -> needs_review) and risk rules
(sensitive account / unbalanced entry -> needs_review).
"""

import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.bookkeeping import run_bookkeeping_agent
from app.agents.document_intake import run_document_intake_agent
from app.agents.reconciliation import run_reconciliation_agent
from app.agents.state import (
    BookkeepingState,
    DocumentIntakeState,
    ReconciliationState,
)

logger = logging.getLogger(__name__)

# Threshold definitions according to ReconAI PRD & System Architecture
CONFIDENCE_THRESHOLD_INTAKE = 0.85
CONFIDENCE_THRESHOLD_BOOKKEEPING = 0.85
CONFIDENCE_THRESHOLD_RECONCILIATION = 0.90


# ==========================================
# 1. Routing Decision Functions
# ==========================================


def route_after_extraction(
    state: DocumentIntakeState,
) -> Literal["proceed_to_bookkeeping", "extraction_review_required", "failed"]:
    """Determine next workflow step after Document Intake Agent execution.

    Rules:
    - If status == 'failed' -> 'failed'
    - If confidence < 0.85, needs_review == True, missing vendor/total
      -> 'extraction_review_required'
    - Else -> 'proceed_to_bookkeeping'
    """
    status = state.get("status")
    confidence = state.get("confidence_score", 0.0)
    needs_review = state.get("needs_review", False)
    vendor_name = state.get("vendor_name")
    total_amount = state.get("total_amount")

    if status == "failed":
        return "failed"

    if (
        confidence < CONFIDENCE_THRESHOLD_INTAKE
        or needs_review
        or status == "extraction_review_required"
        or not vendor_name
        or total_amount is None
    ):
        logger.info(
            "Extraction requires review: conf=%.2f, review=%s, status=%s",
            confidence,
            needs_review,
            status,
        )
        return "extraction_review_required"

    return "proceed_to_bookkeeping"


def route_after_bookkeeping(
    state: BookkeepingState,
) -> Literal["ready_to_post", "bookkeeping_review_required", "failed"]:
    """Determine next workflow step after Bookkeeping Agent execution.

    Rules:
    - If status == 'failed' -> 'failed'
    - If confidence < 0.85, sensitive account used, unbalanced entry,
      needs_review == True, or risk_flags present -> 'bookkeeping_review_required'
    - Else -> 'ready_to_post'
    """
    status = state.get("status")
    confidence = state.get("confidence_score", 0.0)
    uses_sensitive = state.get("uses_sensitive_account", False)
    is_balanced = state.get("is_balanced", True)
    needs_review = state.get("needs_review", False)
    risk_flags = state.get("risk_flags", [])

    if status == "failed":
        return "failed"

    if (
        confidence < CONFIDENCE_THRESHOLD_BOOKKEEPING
        or uses_sensitive
        or not is_balanced
        or needs_review
        or status == "bookkeeping_review_required"
        or bool(risk_flags)
    ):
        logger.info(
            "Bookkeeping requires review: conf=%.2f, sens=%s, bal=%s, risk=%s",
            confidence,
            uses_sensitive,
            is_balanced,
            risk_flags,
        )
        return "bookkeeping_review_required"

    return "ready_to_post"


def route_after_reconciliation(
    state: ReconciliationState,
) -> Literal["matched", "reconciliation_review_required", "failed"]:
    """Determine next workflow step after Reconciliation Agent execution.

    Rules:
    - If status == 'failed' -> 'failed'
    - If confidence < 0.90, recommended_status != 'matched', or needs_review == True
      -> 'reconciliation_review_required'
    - Else -> 'matched'
    """
    status = state.get("status")
    confidence = state.get("confidence_score", 0.0)
    needs_review = state.get("needs_review", False)
    recommended_status = state.get("recommended_status")

    if status == "failed":
        return "failed"

    if (
        confidence < CONFIDENCE_THRESHOLD_RECONCILIATION
        or needs_review
        or recommended_status != "matched"
    ):
        logger.info(
            "Reconciliation requires human review: confidence=%.2f, rec_status=%s",
            confidence,
            recommended_status,
        )
        return "reconciliation_review_required"

    return "matched"


# ==========================================
# 2. LangGraph Execution Nodes
# ==========================================


def document_intake_node(state: DocumentIntakeState) -> DocumentIntakeState:
    """LangGraph node executing Document Intake Agent."""
    logger.info("Executing document_intake_node...")
    response = run_document_intake_agent(
        raw_text=state.get("raw_text"),
        original_filename=state.get("original_filename", "document.pdf"),
        mime_type=state.get("mime_type", "application/pdf"),
        demo_currency=state.get("demo_currency", "IDR"),
    )

    result = response.result
    next_step = route_after_extraction(
        {
            "status": response.status,
            "confidence_score": response.confidence_score,
            "needs_review": response.status == "needs_review",
            "vendor_name": result.vendor_name,
            "total_amount": result.total_amount,
        }
    )

    new_status = (
        "extraction_review_required"
        if next_step == "extraction_review_required"
        else ("extracted" if next_step == "proceed_to_bookkeeping" else "failed")
    )

    return {
        **state,
        "vendor_name": result.vendor_name,
        "transaction_date": result.transaction_date,
        "subtotal_amount": result.subtotal_amount,
        "tax_amount": result.tax_amount,
        "total_amount": result.total_amount,
        "currency": result.currency,
        "line_items": [li.model_dump() for li in result.line_items],
        "extraction_notes": result.extraction_notes,
        "confidence_score": response.confidence_score,
        "rationale": response.rationale,
        "warnings": response.warnings,
        "status": new_status,
        "needs_review": next_step == "extraction_review_required",
    }


def bookkeeping_node(state: BookkeepingState) -> BookkeepingState:
    """LangGraph node executing Bookkeeping Agent."""
    logger.info("Executing bookkeeping_node...")

    extraction_data = {
        "vendor_name": state.get("vendor_name"),
        "transaction_date": state.get("transaction_date"),
        "subtotal_amount": state.get("subtotal_amount"),
        "tax_amount": state.get("tax_amount"),
        "total_amount": state.get("total_amount"),
        "currency": state.get("currency", "IDR"),
        "line_items": state.get("line_items", []),
    }

    coa_list = state.get("chart_of_accounts", [])

    response = run_bookkeeping_agent(
        extraction_data=extraction_data,
        chart_of_accounts=coa_list,
    )

    result = response.result
    next_step = route_after_bookkeeping(
        {
            "status": response.status,
            "confidence_score": response.confidence_score,
            "uses_sensitive_account": result.uses_sensitive_account,
            "is_balanced": result.is_balanced,
            "needs_review": response.status == "needs_review",
            "risk_flags": result.risk_flags,
        }
    )

    new_status = (
        "bookkeeping_review_required"
        if next_step == "bookkeeping_review_required"
        else ("ready_to_post" if next_step == "ready_to_post" else "failed")
    )

    return {
        **state,
        "entry_date": result.entry_date,
        "entry_description": result.description,
        "journal_lines": [jl.model_dump() for jl in result.journal_lines],
        "is_balanced": result.is_balanced,
        "uses_sensitive_account": result.uses_sensitive_account,
        "risk_flags": result.risk_flags,
        "confidence_score": response.confidence_score,
        "rationale": response.rationale,
        "warnings": response.warnings,
        "status": new_status,
        "needs_review": next_step == "bookkeeping_review_required",
    }


def reconciliation_node(state: ReconciliationState) -> ReconciliationState:
    """LangGraph node executing Reconciliation Agent."""
    logger.info("Executing reconciliation_node...")

    bank_tx = state.get("bank_transaction", {})
    candidates = state.get("candidate_journal_entries", [])

    response = run_reconciliation_agent(
        bank_transaction=bank_tx,
        candidate_journal_entries=candidates,
    )

    result = response.result
    next_step = route_after_reconciliation(
        {
            "status": response.status,
            "confidence_score": response.confidence_score,
            "needs_review": response.status == "needs_review",
            "recommended_status": result.recommended_status,
        }
    )

    return {
        **state,
        "candidate_matches": [m.model_dump() for m in result.matches],
        "confidence_score": response.confidence_score,
        "rationale": response.rationale,
        "warnings": response.warnings,
        "status": result.recommended_status,
        "needs_review": next_step == "reconciliation_review_required",
    }


def review_router_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node capturing human review queue payloads when routing to review."""
    logger.info("Executing review_router_node - Routing to Human Review Queue...")
    warnings = list(state.get("warnings", []))
    if "Routed to human review queue for manual verification." not in warnings:
        warnings.append("Routed to human review queue for manual verification.")

    return {
        **state,
        "needs_review": True,
        "warnings": warnings,
    }


# ==========================================
# 3. LangGraph StateGraph DAG Builders
# ==========================================


def build_document_processing_graph() -> Any:
    """Build and compile the Document Intake -> Bookkeeping LangGraph workflow DAG."""
    builder = StateGraph(BookkeepingState)

    # 1. Add nodes
    builder.add_node("document_intake", document_intake_node)
    builder.add_node("bookkeeping", bookkeeping_node)
    builder.add_node("review_router", review_router_node)

    # 2. Set entry point
    builder.add_edge(START, "document_intake")

    # 3. Add conditional edges after extraction
    builder.add_conditional_edges(
        "document_intake",
        route_after_extraction,
        {
            "proceed_to_bookkeeping": "bookkeeping",
            "extraction_review_required": "review_router",
            "failed": END,
        },
    )

    # 4. Add conditional edges after bookkeeping
    builder.add_conditional_edges(
        "bookkeeping",
        route_after_bookkeeping,
        {
            "ready_to_post": END,
            "bookkeeping_review_required": "review_router",
            "failed": END,
        },
    )

    # 5. Review router leads to END
    builder.add_edge("review_router", END)

    return builder.compile()


def build_reconciliation_graph() -> Any:
    """Build and compile the Bank Reconciliation LangGraph workflow DAG."""
    builder = StateGraph(ReconciliationState)

    # 1. Add nodes
    builder.add_node("reconciliation", reconciliation_node)
    builder.add_node("review_router", review_router_node)

    # 2. Set entry point
    builder.add_edge(START, "reconciliation")

    # 3. Add conditional edges after reconciliation
    builder.add_conditional_edges(
        "reconciliation",
        route_after_reconciliation,
        {
            "matched": END,
            "reconciliation_review_required": "review_router",
            "failed": END,
        },
    )

    # 4. Review router leads to END
    builder.add_edge("review_router", END)

    return builder.compile()


# Global compiled graphs instance for reuse across FastAPI routes
document_processing_graph = build_document_processing_graph()
reconciliation_graph = build_reconciliation_graph()
