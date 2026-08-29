"""Bookkeeping Agent for ReconAI.

Maps approved document extraction data into a draft journal entry using LLMs with
Pydantic Structured Outputs and deterministic validation guardrails.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import BOOKKEEPING_SYSTEM_PROMPT
from app.agents.schemas import (
    BookkeepingResponse,
    BookkeepingResult,
    ProposedJournalLine,
)
from app.core.llm import get_llm

logger = logging.getLogger(__name__)


def run_bookkeeping_agent(
    extraction_data: dict[str, Any],
    chart_of_accounts: list[dict[str, Any]],
    provider: str | None = None,
    model_name: str | None = None,
) -> BookkeepingResponse:
    """Execute Bookkeeping Agent to generate a proposed double-entry journal entry.

    Args:
        extraction_data: Dictionary containing extracted document fields
        chart_of_accounts: Reference list of available COA dicts
        provider: Optional LLM provider override ('gemini' or 'openai').
        model_name: Optional LLM model override.

    Returns:
        BookkeepingResponse containing confidence score, rationale, and proposed entry.
    """
    logger.info("Executing Bookkeeping Agent...")

    total_amount = extraction_data.get("total_amount")
    vendor_name = extraction_data.get("vendor_name", "Unknown")

    if total_amount is None or total_amount <= 0:
        logger.warning("Invalid or zero total amount provided for bookkeeping.")
        return BookkeepingResponse(
            agent_name="bookkeeping_agent",
            status="needs_review",
            confidence_score=0.0,
            rationale="Total amount is missing or invalid in extraction data.",
            warnings=["Cannot generate journal entry for zero or missing amount."],
            result=BookkeepingResult(
                entry_date=extraction_data.get("transaction_date") or "2026-01-01",
                description=f"Transaction from {vendor_name}",
                journal_lines=[
                    ProposedJournalLine(
                        account_code="9999",
                        account_name="Suspense Account",
                        description="Unclassified - missing total amount",
                        debit_amount=0.0,
                        credit_amount=0.0,
                    ),
                    ProposedJournalLine(
                        account_code="1010",
                        account_name="Bank Account",
                        description="Payment",
                        debit_amount=0.0,
                        credit_amount=0.0,
                    ),
                ],
                is_balanced=True,
                uses_sensitive_account=True,
                risk_flags=["missing_total_amount", "suspense_account_used"],
            ),
        )

    # Format COA for prompt context
    coa_formatted = "\n".join(
        [
            f"- [{coa.get('account_code')}] {coa.get('account_name')} "
            f"(Type: {coa.get('account_type')}, Normal: {coa.get('normal_balance')}, "
            f"Sensitive: {coa.get('is_sensitive')}) - {coa.get('description', '')}"
            for coa in chart_of_accounts
        ]
    )

    # Create sensitive accounts set for deterministic post-verification
    sensitive_codes = {
        str(coa.get("account_code"))
        for coa in chart_of_accounts
        if coa.get("is_sensitive")
    }

    try:
        llm = get_llm(provider=provider, model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(BookkeepingResponse)

        user_content = (
            f"--- EXTRACTION DATA ---\n"
            f"Vendor Name: {extraction_data.get('vendor_name')}\n"
            f"Transaction Date: {extraction_data.get('transaction_date')}\n"
            f"Subtotal Amount: {extraction_data.get('subtotal_amount')}\n"
            f"Tax Amount (PPN): {extraction_data.get('tax_amount')}\n"
            f"Total Amount: {total_amount}\n"
            f"Currency: {extraction_data.get('currency', 'IDR')}\n"
            f"Document Type: {extraction_data.get('document_type', 'unknown')}\n"
            f"Line Items: {extraction_data.get('line_items', [])}\n"
            f"Extraction Notes: {extraction_data.get('extraction_notes')}\n\n"
            f"--- CHART OF ACCOUNTS REFERENCE ---\n"
            f"{coa_formatted}\n"
        )

        messages = [
            SystemMessage(content=BOOKKEEPING_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        logger.info(
            "Sending extracted data to Bookkeeping LLM Agent (%s)...",
            provider or "default",
        )

        response: BookkeepingResponse = structured_llm.invoke(messages)

        logger.info(
            "🤖 [LLM Bookkeeping] Lines: %d | Conf: %.2f | Rationale: %s",
            len(response.result.journal_lines),
            response.confidence_score,
            response.rationale,
        )
        for line in response.result.journal_lines:
            logger.info(
                "   -> [%s] %s | Dr: %.2f | Cr: %.2f",
                line.account_code,
                line.account_name,
                line.debit_amount,
                line.credit_amount,
            )
        result = response.result
        warnings = list(response.warnings or [])
        risk_flags = list(result.risk_flags or [])

        # Check total debits vs credits
        total_debits = sum(line.debit_amount for line in result.journal_lines)
        total_credits = sum(line.credit_amount for line in result.journal_lines)
        is_balanced = abs(total_debits - total_credits) < 0.01

        if not is_balanced:
            math_err = (
                f"Unbalanced entry: debits={total_debits:.2f}, "
                f"credits={total_credits:.2f}"
            )
            warnings.append(math_err)
            risk_flags.append("unbalanced_entry")

        # Check sensitive account usage deterministically
        uses_sensitive = (
            any(
                str(line.account_code) in sensitive_codes
                for line in result.journal_lines
            )
            or result.uses_sensitive_account
        )

        if uses_sensitive and "uses_sensitive_account" not in risk_flags:
            risk_flags.append("uses_sensitive_account")

        # Check if Suspense Account (9999) was used
        if any(str(line.account_code) == "9999" for line in result.journal_lines):
            if "suspense_account_used" not in risk_flags:
                risk_flags.append("suspense_account_used")

        # Routing logic: sensitive accounts OR unbalanced entries MUST require review!
        if uses_sensitive or not is_balanced or "suspense_account_used" in risk_flags:
            status = "needs_review"
            confidence = min(response.confidence_score, 0.80)
        else:
            status = response.status
            confidence = response.confidence_score

        updated_result = BookkeepingResult(
            entry_date=result.entry_date,
            description=result.description,
            journal_lines=result.journal_lines,
            is_balanced=is_balanced,
            uses_sensitive_account=uses_sensitive,
            risk_flags=risk_flags,
        )

        return BookkeepingResponse(
            agent_name="bookkeeping_agent",
            status=status,
            confidence_score=confidence,
            rationale=response.rationale,
            warnings=warnings,
            result=updated_result,
        )

    except Exception as e:
        logger.error("Error executing Bookkeeping Agent: %s", str(e), exc_info=True)
        return BookkeepingResponse(
            agent_name="bookkeeping_agent",
            status="failed",
            confidence_score=0.0,
            rationale=f"LLM execution error: {str(e)}",
            warnings=[f"Execution exception: {str(e)}"],
            result=BookkeepingResult(
                entry_date=extraction_data.get("transaction_date") or "2026-01-01",
                description="Failed bookkeeping generation",
                journal_lines=[
                    ProposedJournalLine(
                        account_code="9999",
                        account_name="Suspense Account",
                        debit_amount=float(total_amount or 0.0),
                        credit_amount=0.0,
                    ),
                    ProposedJournalLine(
                        account_code="1010",
                        account_name="Bank Account",
                        debit_amount=0.0,
                        credit_amount=float(total_amount or 0.0),
                    ),
                ],
                is_balanced=True,
                uses_sensitive_account=True,
                risk_flags=["execution_failed"],
            ),
        )
