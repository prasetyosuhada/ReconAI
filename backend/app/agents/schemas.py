"""Structured Output (Pydantic Models) for ReconAI AI Agents.

These models define the strict JSON schemas enforced when invoking Gemini/OpenAI
structured output LLM calls across Document Intake, Bookkeeping, and Reconciliation.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ==========================================
# 1. Document Intake Agent Schemas
# ==========================================


class ExtractedLineItem(BaseModel):
    """Line item detail extracted from an invoice or receipt."""

    description: str = Field(
        ..., description="Description of product or service purchased"
    )
    quantity: float | None = Field(
        default=None, description="Quantity purchased if visible"
    )
    unit_price: float | None = Field(
        default=None, description="Price per unit if visible"
    )
    amount: float | None = Field(default=None, description="Total line item amount")


class DocumentExtractionResult(BaseModel):
    """Structured extraction payload from an invoice/receipt."""

    document_type: Literal["invoice", "receipt", "unknown"] = Field(
        default="unknown", description="Classification of the document"
    )
    vendor_name: str | None = Field(
        default=None, description="Name of the seller or merchant"
    )
    transaction_date: str | None = Field(
        default=None, description="Transaction or invoice date (YYYY-MM-DD)"
    )
    currency: str = Field(
        default="IDR", description="ISO 4217 currency code (e.g. IDR, USD)"
    )
    subtotal_amount: float | None = Field(
        default=None, description="Subtotal amount before tax"
    )
    tax_amount: float | None = Field(
        default=None, description="Tax amount (e.g. VAT / PPN)"
    )
    total_amount: float | None = Field(
        default=None, description="Final total transaction amount"
    )
    line_items: list[ExtractedLineItem] = Field(
        default_factory=list, description="Extracted line item items"
    )
    extraction_notes: str | None = Field(
        default=None, description="Agent notes on document quality or ambiguity"
    )


class DocumentIntakeResponse(BaseModel):
    """Complete envelope returned by Document Intake Agent."""

    agent_name: str = Field(
        default="document_intake_agent", description="Agent identifier"
    )
    status: Literal["completed", "needs_review", "failed"] = Field(
        ..., description="Extraction execution status"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Extraction confidence score"
    )
    rationale: str = Field(..., description="Human-readable rationale for extraction")
    warnings: list[str] = Field(
        default_factory=list, description="Ambiguity or missing field warnings"
    )
    result: DocumentExtractionResult = Field(
        ..., description="Extracted document payload"
    )


# ==========================================
# 2. Bookkeeping Agent Schemas
# ==========================================


class ProposedJournalLine(BaseModel):
    """Debit or Credit line item within a proposed Journal Entry."""

    account_code: str = Field(
        ..., description="Chart of Accounts code (e.g. '5100', '1010')"
    )
    account_name: str = Field(..., description="Chart of Accounts display name")
    description: str | None = Field(
        default=None, description="Line-level accounting memo"
    )
    debit_amount: float = Field(
        default=0.0, ge=0.0, description="Debit amount (>= 0.0)"
    )
    credit_amount: float = Field(
        default=0.0, ge=0.0, description="Credit amount (>= 0.0)"
    )


class BookkeepingResult(BaseModel):
    """Structured bookkeeping suggestion payload."""

    entry_date: str = Field(
        ..., description="Accounting date for the entry (YYYY-MM-DD)"
    )
    description: str = Field(..., description="Header journal entry description")
    journal_lines: list[ProposedJournalLine] = Field(
        ..., min_items=2, description="Double-entry lines (minimum 2 lines)"
    )
    is_balanced: bool = Field(
        ..., description="Whether sum of debits equals sum of credits"
    )
    uses_sensitive_account: bool = Field(
        default=False,
        description="Whether any sensitive COA account was selected",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Risk flags (low confidence, sensitive, suspense account)",
    )


class BookkeepingResponse(BaseModel):
    """Complete envelope returned by Bookkeeping Agent."""

    agent_name: str = Field(default="bookkeeping_agent", description="Agent identifier")
    status: Literal["completed", "needs_review", "failed"] = Field(
        ..., description="Bookkeeping execution status"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Bookkeeping confidence score"
    )
    rationale: str = Field(..., description="Accounting classification rationale")
    warnings: list[str] = Field(
        default_factory=list, description="Classification warnings or risk notes"
    )
    result: BookkeepingResult = Field(..., description="Proposed journal entry payload")


# ==========================================
# 3. Reconciliation Agent Schemas
# ==========================================


class ProposedMatchCandidate(BaseModel):
    """Candidate match between a bank transaction and a journal entry."""

    journal_entry_id: str = Field(..., description="Candidate posted Journal Entry ID")
    match_type: Literal["exact", "fuzzy", "unmatched"] = Field(
        ..., description="Match category"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall match confidence"
    )
    amount_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Amount similarity score"
    )
    date_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Date proximity score"
    )
    vendor_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Vendor similarity score"
    )
    rationale: str = Field(
        ..., description="Explanation of why this candidate was matched"
    )


class ReconciliationResult(BaseModel):
    """Structured reconciliation result payload."""

    bank_transaction_id: str = Field(
        ..., description="ID of bank transaction being matched"
    )
    matches: list[ProposedMatchCandidate] = Field(
        default_factory=list, description="Ranked candidate matches"
    )
    recommended_status: Literal[
        "matched", "possible_match_review_required", "unmatched_review_required"
    ] = Field(..., description="Recommended workflow status for bank transaction")


class ReconciliationResponse(BaseModel):
    """Complete envelope returned by Reconciliation Agent."""

    agent_name: str = Field(
        default="reconciliation_agent", description="Agent identifier"
    )
    status: Literal["completed", "needs_review", "failed"] = Field(
        ..., description="Reconciliation execution status"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall match confidence score"
    )
    rationale: str = Field(
        ..., description="Summary explanation of reconciliation result"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Reconciliation warnings"
    )
    result: ReconciliationResult = Field(
        ..., description="Reconciliation matching result payload"
    )
