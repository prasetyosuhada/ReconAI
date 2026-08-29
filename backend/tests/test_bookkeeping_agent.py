from unittest.mock import MagicMock, patch

from app.agents.bookkeeping import run_bookkeeping_agent
from app.agents.schemas import (
    BookkeepingResponse,
    BookkeepingResult,
    ProposedJournalLine,
)

MOCK_COA = [
    {
        "account_code": "1010",
        "account_name": "Bank Account",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": True,
    },
    {
        "account_code": "5100",
        "account_name": "Office Supplies Expense",
        "account_type": "expense",
        "normal_balance": "debit",
        "is_sensitive": False,
    },
    {
        "account_code": "9999",
        "account_name": "Suspense Account",
        "account_type": "asset",
        "normal_balance": "debit",
        "is_sensitive": True,
    },
]


def test_bookkeeping_agent_missing_amount():
    response = run_bookkeeping_agent(
        extraction_data={"vendor_name": "Acme", "total_amount": 0},
        chart_of_accounts=MOCK_COA,
    )
    assert response.status == "needs_review"
    assert response.confidence_score == 0.0
    assert "missing_total_amount" in response.result.risk_flags


@patch("app.agents.bookkeeping.get_llm")
def test_bookkeeping_agent_sensitive_account_routing(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = BookkeepingResponse(
        agent_name="bookkeeping_agent",
        status="completed",
        confidence_score=0.92,
        rationale="Office supplies purchase.",
        warnings=[],
        result=BookkeepingResult(
            entry_date="2026-07-20",
            description="Office supplies from Acme",
            journal_lines=[
                ProposedJournalLine(
                    account_code="5100",
                    account_name="Office Supplies Expense",
                    debit_amount=50000.0,
                    credit_amount=0.0,
                ),
                ProposedJournalLine(
                    account_code="1010",
                    account_name="Bank Account",
                    debit_amount=0.0,
                    credit_amount=50000.0,
                ),
            ],
            is_balanced=True,
            uses_sensitive_account=False,
            risk_flags=[],
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_bookkeeping_agent(
        extraction_data={
            "vendor_name": "Acme",
            "transaction_date": "2026-07-20",
            "subtotal_amount": 45000.0,
            "tax_amount": 5000.0,
            "total_amount": 50000.0,
        },
        chart_of_accounts=MOCK_COA,
    )

    system_prompt, user_prompt = mock_structured_llm.invoke.call_args.args[0]
    assert (
        "Handle recoverable Input VAT (PPN Masukan) explicitly" in system_prompt.content
    )
    assert "Subtotal Amount: 45000.0" in user_prompt.content
    assert "Tax Amount (PPN): 5000.0" in user_prompt.content

    # 1010 Bank Account is sensitive -> MUST force status to needs_review!
    assert response.status == "needs_review"
    assert response.result.uses_sensitive_account is True
    assert "uses_sensitive_account" in response.result.risk_flags


@patch("app.agents.bookkeeping.get_llm")
def test_bookkeeping_agent_unbalanced_entry_routing(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = BookkeepingResponse(
        agent_name="bookkeeping_agent",
        status="completed",
        confidence_score=0.90,
        rationale="Unbalanced test.",
        warnings=[],
        result=BookkeepingResult(
            entry_date="2026-07-20",
            description="Unbalanced test",
            journal_lines=[
                ProposedJournalLine(
                    account_code="5100",
                    account_name="Office Supplies Expense",
                    debit_amount=50000.0,
                    credit_amount=0.0,
                ),
                ProposedJournalLine(
                    account_code="5100",
                    account_name="Office Supplies Expense",
                    debit_amount=0.0,
                    credit_amount=40000.0,  # Unbalanced
                ),
            ],
            is_balanced=True,
            uses_sensitive_account=False,
            risk_flags=[],
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_bookkeeping_agent(
        extraction_data={"total_amount": 50000.0},
        chart_of_accounts=MOCK_COA,
    )

    assert response.status == "needs_review"
    assert response.result.is_balanced is False
    assert "unbalanced_entry" in response.result.risk_flags
