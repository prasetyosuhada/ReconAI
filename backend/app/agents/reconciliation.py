"""Reconciliation Agent for ReconAI.

Matches bank statement transactions against candidate posted journal entries using LLMs
with Pydantic Structured Outputs and deterministic heuristic fallback checks.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import RECONCILIATION_SYSTEM_PROMPT
from app.agents.schemas import (
    ReconciliationResponse,
    ReconciliationResult,
)
from app.core.llm import get_llm

logger = logging.getLogger(__name__)


def run_reconciliation_agent(
    bank_transaction: dict[str, Any],
    candidate_journal_entries: list[dict[str, Any]],
    provider: str | None = None,
    model_name: str | None = None,
) -> ReconciliationResponse:
    """Execute Reconciliation Agent to match a bank transaction to posted entries.

    Args:
        bank_transaction: Dict containing bank transaction fields
            (id, transaction_date, description, amount, currency)
        candidate_journal_entries: List of dicts representing candidate posted entries
        provider: Optional LLM provider override ('gemini' or 'openai').
        model_name: Optional LLM model override.

    Returns:
        ReconciliationResponse containing ranked matches, confidence score, and status.
    """
    bank_tx_id = str(bank_transaction.get("id", "unknown"))
    logger.info("Executing Reconciliation Agent for transaction: %s", bank_tx_id)

    # Deterministic check: if no candidate entries provided
    if not candidate_journal_entries:
        logger.info(
            "No candidate journal entries provided for transaction %s", bank_tx_id
        )
        return ReconciliationResponse(
            agent_name="reconciliation_agent",
            status="needs_review",
            confidence_score=0.30,
            rationale="No candidate posted journal entries available to match against.",
            warnings=["No posted journal entry candidates found in the database."],
            result=ReconciliationResult(
                bank_transaction_id=bank_tx_id,
                matches=[],
                recommended_status="unmatched_review_required",
            ),
        )

    # Format candidates for prompt context
    formatted_lines = []
    for c in candidate_journal_entries:
        amt = c.get("total_debit") or c.get("total_credit") or 0.0
        formatted_lines.append(
            f"- Entry ID: [{c.get('id')}] Date: {c.get('entry_date')} | "
            f"Desc: {c.get('description')} | Amount: {amt} | "
            f"Accounts: {c.get('accounts', [])}"
        )
    candidates_formatted = "\n".join(formatted_lines)

    try:
        llm = get_llm(provider=provider, model_name=model_name, temperature=0.0)
        structured_llm = llm.with_structured_output(ReconciliationResponse)

        user_content = (
            f"--- BANK TRANSACTION ---\n"
            f"Transaction ID: {bank_tx_id}\n"
            f"Transaction Date: {bank_transaction.get('transaction_date')}\n"
            f"Description: {bank_transaction.get('description')}\n"
            f"Amount: {bank_transaction.get('amount')}\n"
            f"Currency: {bank_transaction.get('currency', 'IDR')}\n\n"
            f"--- CANDIDATE POSTED JOURNAL ENTRIES ---\n"
            f"{candidates_formatted}\n"
        )

        messages = [
            SystemMessage(content=RECONCILIATION_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        response: ReconciliationResponse = structured_llm.invoke(messages)

        result = response.result
        warnings = list(response.warnings or [])
        matches = list(result.matches or [])

        # Post-processing heuristics
        if not matches:
            recommended_status = "unmatched_review_required"
            status = "needs_review"
            confidence = min(response.confidence_score, 0.50)
            if "No matches returned by agent." not in warnings:
                warnings.append("No matches returned by agent.")
        else:
            # Check for ambiguous competing top matches
            high_confidence_matches = [m for m in matches if m.confidence_score >= 0.85]
            if len(high_confidence_matches) > 1:
                ambiguity_warn = (
                    f"Multiple competing candidate matches found "
                    f"({len(high_confidence_matches)} candidates >= 0.85)."
                )
                if ambiguity_warn not in warnings:
                    warnings.append(ambiguity_warn)
                recommended_status = "possible_match_review_required"
                status = "needs_review"
                confidence = min(response.confidence_score, 0.80)
            else:
                recommended_status = result.recommended_status
                status = response.status
                confidence = response.confidence_score

        updated_result = ReconciliationResult(
            bank_transaction_id=bank_tx_id,
            matches=matches,
            recommended_status=recommended_status,
        )

        return ReconciliationResponse(
            agent_name="reconciliation_agent",
            status=status,
            confidence_score=confidence,
            rationale=response.rationale,
            warnings=warnings,
            result=updated_result,
        )

    except Exception as e:
        logger.error("Error executing Reconciliation Agent: %s", str(e), exc_info=True)
        return ReconciliationResponse(
            agent_name="reconciliation_agent",
            status="failed",
            confidence_score=0.0,
            rationale=f"LLM execution error: {str(e)}",
            warnings=[f"Execution exception: {str(e)}"],
            result=ReconciliationResult(
                bank_transaction_id=bank_tx_id,
                matches=[],
                recommended_status="unmatched_review_required",
            ),
        )
