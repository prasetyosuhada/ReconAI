from unittest.mock import MagicMock, patch

from app.agents.reconciliation import run_reconciliation_agent
from app.agents.schemas import (
    ProposedMatchCandidate,
    ReconciliationResponse,
    ReconciliationResult,
)


def test_reconciliation_agent_no_candidates():
    response = run_reconciliation_agent(
        bank_transaction={"id": "bt-1", "amount": -50000.0},
        candidate_journal_entries=[],
    )
    assert response.status == "needs_review"
    assert response.result.recommended_status == "unmatched_review_required"
    assert len(response.result.matches) == 0


@patch("app.agents.reconciliation.get_llm")
def test_reconciliation_agent_exact_match_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = ReconciliationResponse(
        agent_name="reconciliation_agent",
        status="completed",
        confidence_score=0.95,
        rationale="Exact amount and date match.",
        warnings=[],
        result=ReconciliationResult(
            bank_transaction_id="bt-1",
            matches=[
                ProposedMatchCandidate(
                    journal_entry_id="je-1",
                    match_type="exact",
                    confidence_score=0.95,
                    amount_score=1.0,
                    date_score=0.9,
                    vendor_score=0.95,
                    rationale="Exact amount and close date.",
                )
            ],
            recommended_status="matched",
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_reconciliation_agent(
        bank_transaction={
            "id": "bt-1",
            "transaction_date": "2026-07-22",
            "description": "GRAMEDIA STORE",
            "amount": -111000.0,
        },
        candidate_journal_entries=[
            {
                "id": "je-1",
                "entry_date": "2026-07-20",
                "description": "Toko Gramedia purchase",
                "total_debit": 111000.0,
            }
        ],
    )

    assert response.status == "completed"
    assert response.result.recommended_status == "matched"
    assert len(response.result.matches) == 1
    assert response.result.matches[0].journal_entry_id == "je-1"


@patch("app.agents.reconciliation.get_llm")
def test_reconciliation_agent_competing_matches_heuristic(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = ReconciliationResponse(
        agent_name="reconciliation_agent",
        status="completed",
        confidence_score=0.92,
        rationale="Found candidate matches.",
        warnings=[],
        result=ReconciliationResult(
            bank_transaction_id="bt-1",
            matches=[
                ProposedMatchCandidate(
                    journal_entry_id="je-1",
                    match_type="fuzzy",
                    confidence_score=0.90,
                    rationale="Candidate 1",
                ),
                ProposedMatchCandidate(
                    journal_entry_id="je-2",
                    match_type="fuzzy",
                    confidence_score=0.88,
                    rationale="Candidate 2",
                ),
            ],
            recommended_status="matched",
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_reconciliation_agent(
        bank_transaction={"id": "bt-1", "amount": -100000.0},
        candidate_journal_entries=[
            {"id": "je-1", "total_debit": 100000.0},
            {"id": "je-2", "total_debit": 100000.0},
        ],
    )

    # Multiple candidates >= 0.85 -> Heuristic must force status
    # to needs_review & possible_match_review_required
    assert response.status == "needs_review"
    assert response.result.recommended_status == "possible_match_review_required"
    assert any("Multiple competing candidate matches" in w for w in response.warnings)
