"""LangGraph State Schemas for ReconAI Agentic Workflows.

This module defines the TypedDict state representations used by LangGraph nodes
and edges, as well as Pydantic models for structured agent input/output envelopes.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

# ==========================================
# 1. Shared Agent Output Pydantic Envelopes
# ==========================================


class SharedAgentOutput(BaseModel):
    """Standard envelope returned by all ReconAI AI Agents."""

    agent_name: str = Field(..., description="Stable identifier of the agent")
    status: Literal["completed", "needs_review", "failed"] = Field(
        ..., description="Execution lifecycle status"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Explicit confidence score (0.0 to 1.0)"
    )
    rationale: str = Field(
        ..., description="Human-readable explanation of agent decision"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings or ambiguity notes"
    )
    result: dict[str, Any] = Field(
        default_factory=dict, description="Structured agent-specific output"
    )


# ==========================================
# 2. LangGraph Workflow TypedDict States
# ==========================================


class DocumentIntakeState(TypedDict, total=False):
    """State schema for Document Intake Agent & Workflow."""

    document_id: str
    original_filename: str
    mime_type: str
    stored_file_path: str
    demo_currency: str
    raw_text: str | None

    # Extraction output
    extraction_id: str | None
    vendor_name: str | None
    transaction_date: str | None
    subtotal_amount: float | None
    tax_amount: float | None
    total_amount: float | None
    currency: str
    line_items: list[dict[str, Any]]
    extraction_notes: str | None

    # Agent envelope state
    confidence_score: float
    rationale: str
    warnings: Annotated[list[str], operator.add]
    status: str  # uploaded, extracting, extraction_review_required, extracted, failed
    needs_review: bool
    review_id: str | None
    error: str | None


class BookkeepingState(TypedDict, total=False):
    """State schema for Bookkeeping Agent & Workflow."""

    document_id: str | None
    original_filename: str
    mime_type: str
    stored_file_path: str
    demo_currency: str
    raw_text: str | None
    extraction_id: str | None
    vendor_name: str | None
    transaction_date: str | None
    subtotal_amount: float | None
    tax_amount: float | None
    total_amount: float | None
    currency: str
    line_items: list[dict[str, Any]]

    # Available COA reference context
    chart_of_accounts: list[dict[str, Any]]

    # Draft Journal Entry Output
    journal_entry_id: str | None
    entry_date: str | None
    entry_description: str | None
    journal_lines: list[dict[str, Any]]
    proposed_journal: list[dict[str, Any]]

    # Validation & Risk
    is_balanced: bool
    total_debit: float
    total_credit: float
    uses_sensitive_account: bool
    risk_flags: list[str]

    # Agent envelope state
    confidence_score: float
    rationale: str
    warnings: Annotated[list[str], operator.add]
    status: str  # draft, bookkeeping_review_required, ready_to_post, posted, rejected
    needs_review: bool
    review_id: str | None
    error: str | None


class ReconciliationState(TypedDict, total=False):
    """State schema for Reconciliation Agent & Workflow."""

    bank_statement_import_id: str | None
    bank_transaction_id: str
    bank_transaction: dict[
        str, Any
    ]  # id, transaction_date, description, amount, currency
    candidate_journal_entries: list[dict[str, Any]]

    # Matching result
    match_id: str | None
    matched_journal_entry_id: str | None
    match_type: str  # exact, fuzzy, manual, unmatched
    amount_score: float | None
    date_score: float | None
    vendor_score: float | None
    candidate_matches: list[dict[str, Any]]

    # Agent envelope state
    confidence_score: float
    rationale: str
    warnings: Annotated[list[str], operator.add]
    status: str
    needs_review: bool
    review_id: str | None
    error: str | None


class ReconAIOverallState(TypedDict, total=False):
    """Unified Orchestration State across Document, Bookkeeping, and Reconciliation."""

    workflow_id: str
    workflow_type: Literal["document_processing", "reconciliation"]
    current_step: str

    # Document & Extraction state
    document_id: str | None
    extraction_id: str | None
    document_state: DocumentIntakeState | None

    # Bookkeeping & Journal state
    journal_entry_id: str | None
    bookkeeping_state: BookkeepingState | None

    # Reconciliation state
    bank_transaction_id: str | None
    reconciliation_state: ReconciliationState | None

    # System & Audit state
    review_items: Annotated[list[dict[str, Any]], operator.add]
    audit_events: Annotated[list[dict[str, Any]], operator.add]
    is_completed: bool
    error: str | None
