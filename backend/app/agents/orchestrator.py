"""Orchestrator Routing Logic and LangGraph Nodes for ReconAI.

Provides deterministic conditional routing functions and LangGraph workflow nodes
to enforce confidence thresholds (confidence < 0.85 -> needs_review) and risk rules
(sensitive account / unbalanced entry -> needs_review).
"""

import logging
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.bookkeeping import (
    classify_bookkeeping,
    route_after_bookkeeping,
)
from app.agents.document_intake import run_document_intake_agent
from app.agents.reconciliation import run_reconciliation_agent
from app.agents.state import (
    DocumentIntakeState,
    DocumentProcessingState,
    ReconciliationState,
)

logger = logging.getLogger(__name__)

# Threshold definitions according to ReconAI PRD & System Architecture
CONFIDENCE_THRESHOLD_INTAKE = 0.85
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


def document_intake_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """LangGraph node executing Document Intake Agent."""
    logger.info("Executing document_intake_node...")
    response = run_document_intake_agent(
        raw_text=state.get("raw_text"),
        image_base64=state.get("image_base64"),
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
        "document_type": result.document_type,
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
        "low_confidence_fields": response.low_confidence_fields,
        "status": new_status,
        "needs_review": next_step == "extraction_review_required",
    }


def bookkeeping_node(state: DocumentProcessingState) -> DocumentProcessingState:
    """LangGraph node executing Bookkeeping Agent."""
    logger.info("Executing bookkeeping_node...")

    extraction_data = {
        "document_type": state.get("document_type", "unknown"),
        "vendor_name": state.get("vendor_name"),
        "transaction_date": state.get("transaction_date"),
        "subtotal_amount": state.get("subtotal_amount"),
        "tax_amount": state.get("tax_amount"),
        "total_amount": state.get("total_amount"),
        "currency": state.get("currency", "IDR"),
        "line_items": state.get("line_items", []),
        "extraction_notes": state.get("extraction_notes"),
    }

    coa_list = state.get("chart_of_accounts", [])

    outcome = classify_bookkeeping(
        extraction_data=extraction_data,
        chart_of_accounts=coa_list,
    )

    return {
        **state,
        "entry_date": outcome.entry_date,
        "entry_description": outcome.entry_description,
        "journal_lines": outcome.journal_lines,
        "proposed_journal": outcome.journal_lines,
        "total_debit": outcome.total_debit,
        "total_credit": outcome.total_credit,
        "is_balanced": outcome.is_balanced,
        "uses_sensitive_account": outcome.uses_sensitive_account,
        "risk_flags": outcome.risk_flags,
        "confidence_score": outcome.confidence_score,
        "rationale": outcome.rationale,
        "warnings": outcome.warnings,
        "status": outcome.status,
        "needs_review": outcome.needs_review,
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
        "recommended_status": result.recommended_status,
        "confidence_score": response.confidence_score,
        "rationale": response.rationale,
        "warnings": response.warnings,
        "status": (
            "failed" if response.status == "failed" else result.recommended_status
        ),
        "needs_review": next_step == "reconciliation_review_required",
        "error": response.rationale if response.status == "failed" else None,
    }


def review_router_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node capturing human review queue payloads when routing to review."""
    logger.info("Executing review_router_node - Routing to Human Review Queue...")
    review_warning = "Routed to human review queue for manual verification."
    warnings = state.get("warnings", [])

    # `warnings` uses an additive reducer. Return only the new warning instead of
    # copying the complete accumulated list, otherwise previous warnings duplicate.
    return {
        "needs_review": True,
        "warnings": [] if review_warning in warnings else [review_warning],
    }


# ==========================================
# 3. LangGraph StateGraph DAG Builders
# ==========================================


def build_document_processing_graph() -> Any:
    """Build and compile the Document Intake -> Bookkeeping LangGraph workflow DAG."""
    builder = StateGraph(DocumentProcessingState)

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
