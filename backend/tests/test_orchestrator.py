from unittest.mock import MagicMock, patch

from app.agents.orchestrator import (
    document_processing_graph,
    reconciliation_graph,
    route_after_bookkeeping,
    route_after_extraction,
    route_after_reconciliation,
)
from app.agents.schemas import (
    BookkeepingResponse,
    BookkeepingResult,
    DocumentExtractionResult,
    DocumentIntakeResponse,
    ProposedJournalLine,
    ProposedMatchCandidate,
    ReconciliationResponse,
    ReconciliationResult,
)


def test_route_after_extraction_success():
    next_step = route_after_extraction(
        {
            "status": "completed",
            "confidence_score": 0.95,
            "needs_review": False,
            "vendor_name": "Toko Gramedia",
            "total_amount": 100000.0,
        }
    )
    assert next_step == "proceed_to_bookkeeping"


def test_route_after_extraction_low_confidence():
    next_step = route_after_extraction(
        {
            "status": "needs_review",
            "confidence_score": 0.80,  # < 0.85 threshold
            "needs_review": True,
            "vendor_name": "Toko Gramedia",
            "total_amount": 100000.0,
        }
    )
    assert next_step == "extraction_review_required"


def test_route_after_extraction_missing_fields():
    next_step = route_after_extraction(
        {
            "status": "completed",
            "confidence_score": 0.90,
            "needs_review": False,
            "vendor_name": None,  # Missing vendor
            "total_amount": 100000.0,
        }
    )
    assert next_step == "extraction_review_required"


def test_route_after_bookkeeping_success():
    next_step = route_after_bookkeeping(
        {
            "status": "completed",
            "confidence_score": 0.92,
            "uses_sensitive_account": False,
            "is_balanced": True,
            "needs_review": False,
            "risk_flags": [],
        }
    )
    assert next_step == "ready_to_post"


def test_route_after_bookkeeping_sensitive_account():
    next_step = route_after_bookkeeping(
        {
            "status": "needs_review",
            "confidence_score": 0.95,
            "uses_sensitive_account": True,  # Sensitive account trigger
            "is_balanced": True,
            "needs_review": True,
            "risk_flags": ["uses_sensitive_account"],
        }
    )
    assert next_step == "bookkeeping_review_required"


def test_route_after_bookkeeping_unbalanced():
    next_step = route_after_bookkeeping(
        {
            "status": "needs_review",
            "confidence_score": 0.90,
            "uses_sensitive_account": False,
            "is_balanced": False,  # Unbalanced entry trigger
            "needs_review": True,
            "risk_flags": ["unbalanced_entry"],
        }
    )
    assert next_step == "bookkeeping_review_required"


def test_route_after_reconciliation_success():
    next_step = route_after_reconciliation(
        {
            "status": "completed",
            "confidence_score": 0.95,
            "needs_review": False,
            "recommended_status": "matched",
        }
    )
    assert next_step == "matched"


def test_route_after_reconciliation_review_required():
    next_step = route_after_reconciliation(
        {
            "status": "needs_review",
            "confidence_score": 0.80,
            "needs_review": True,
            "recommended_status": "possible_match_review_required",
        }
    )
    assert next_step == "reconciliation_review_required"


@patch(
    "app.agents.orchestrator.perf_counter",
    side_effect=[100.0, 100.25, 200.0, 200.75],
)
@patch("app.agents.document_intake.get_llm")
@patch("app.agents.bookkeeping.get_llm")
def test_document_processing_graph_splits_input_vat(
    mock_bookkeeping_llm, mock_intake_llm, mock_perf_counter
):
    # Setup Document Intake Agent mock response
    mock_intake_base = MagicMock()
    mock_intake_struct = MagicMock()
    mock_intake_struct.invoke.return_value = DocumentIntakeResponse(
        agent_name="document_intake_agent",
        status="completed",
        confidence_score=0.95,
        rationale="High quality extraction",
        warnings=[],
        result=DocumentExtractionResult(
            document_type="invoice",
            vendor_name="PT Media Utama",
            transaction_date="2026-08-01",
            currency="IDR",
            subtotal_amount=500000.0,
            tax_amount=55000.0,
            total_amount=555000.0,
            line_items=[],
        ),
    )
    mock_intake_base.with_structured_output.return_value = mock_intake_struct
    mock_intake_llm.return_value = mock_intake_base

    # Setup Bookkeeping Agent mock response (non-sensitive account)
    mock_bk_base = MagicMock()
    mock_bk_struct = MagicMock()
    mock_bk_struct.invoke.return_value = BookkeepingResponse(
        agent_name="bookkeeping_agent",
        status="completed",
        confidence_score=0.90,
        rationale="Office supplies classification",
        warnings=[],
        result=BookkeepingResult(
            entry_date="2026-08-01",
            description="Purchase from PT Media Utama",
            journal_lines=[
                ProposedJournalLine(
                    account_code="5100",
                    account_name="Office Supplies Expense",
                    debit_amount=500000.0,
                    credit_amount=0.0,
                ),
                ProposedJournalLine(
                    account_code="1400",
                    account_name="Input VAT",
                    debit_amount=55000.0,
                    credit_amount=0.0,
                ),
                ProposedJournalLine(
                    account_code="2000",
                    account_name="Accounts Payable",
                    debit_amount=0.0,
                    credit_amount=555000.0,
                ),
            ],
            is_balanced=True,
            uses_sensitive_account=False,
            risk_flags=[],
        ),
    )
    mock_bk_base.with_structured_output.return_value = mock_bk_struct
    mock_bookkeeping_llm.return_value = mock_bk_base

    # Invoke compiled LangGraph DAG
    initial_state = {
        "raw_text": "PT Media Utama Invoice Total 555000",
        "original_filename": "invoice_media.pdf",
        "chart_of_accounts": [
            {
                "account_code": "5100",
                "account_name": "Office Supplies",
                "is_sensitive": False,
            },
            {
                "account_code": "1400",
                "account_name": "Input VAT",
                "is_sensitive": False,
            },
            {
                "account_code": "2000",
                "account_name": "Accounts Payable",
                "is_sensitive": False,
            },
        ],
    }

    final_state = document_processing_graph.invoke(initial_state)

    assert final_state["vendor_name"] == "PT Media Utama"
    assert final_state["subtotal_amount"] == 500000.0
    assert final_state["tax_amount"] == 55000.0
    assert final_state["total_amount"] == 555000.0
    assert final_state["status"] == "ready_to_post"
    assert final_state["needs_review"] is False
    assert final_state["proposed_journal"] == final_state["journal_lines"]
    assert final_state["intake_confidence_score"] == 0.95
    assert final_state["intake_rationale"] == "High quality extraction"
    assert final_state["intake_status"] == "extracted"
    assert final_state["intake_needs_review"] is False
    assert final_state["intake_processing_duration_ms"] == 250.0
    assert final_state["bookkeeping_confidence_score"] == 0.90
    assert final_state["bookkeeping_rationale"] == "Office supplies classification"
    assert final_state["bookkeeping_status"] == "ready_to_post"
    assert final_state["bookkeeping_needs_review"] is False
    assert final_state["bookkeeping_processing_duration_ms"] == 750.0
    assert mock_perf_counter.call_count == 4

    journal_lines = final_state["journal_lines"]
    input_vat_lines = [line for line in journal_lines if line["account_code"] == "1400"]
    assert len(input_vat_lines) == 1
    assert input_vat_lines[0]["debit_amount"] == final_state["tax_amount"]
    assert input_vat_lines[0]["credit_amount"] == 0.0

    expense_lines = [line for line in journal_lines if line["account_code"] == "5100"]
    assert (
        sum(line["debit_amount"] for line in expense_lines)
        == final_state["subtotal_amount"]
    )
    assert final_state["total_debit"] == final_state["total_credit"]
    assert final_state["total_debit"] == final_state["total_amount"]
    assert final_state["is_balanced"] is True


def test_reconciliation_graph_end_to_end_unmatched():
    initial_state = {
        "bank_transaction": {"id": "tx-100", "amount": 250000.0},
        "candidate_journal_entries": [],
    }

    final_state = reconciliation_graph.invoke(initial_state)

    assert final_state["needs_review"] is True
    assert final_state["status"] == "unmatched_review_required"


@patch("app.agents.orchestrator.run_reconciliation_agent")
def test_reconciliation_graph_end_to_end_matched(mock_agent):
    mock_agent.return_value = ReconciliationResponse(
        agent_name="reconciliation_agent",
        status="completed",
        confidence_score=0.95,
        rationale="Single strong candidate match.",
        result=ReconciliationResult(
            bank_transaction_id="tx-101",
            matches=[
                ProposedMatchCandidate(
                    journal_entry_id="je-101",
                    match_type="exact",
                    confidence_score=0.95,
                    amount_score=1.0,
                    date_score=0.95,
                    vendor_score=0.9,
                    rationale="Amount and date align.",
                )
            ],
            recommended_status="matched",
        ),
    )

    updates = list(
        reconciliation_graph.stream(
            {
                "bank_transaction": {"id": "tx-101", "amount": 250000.0},
                "candidate_journal_entries": [{"id": "je-101"}],
            },
            stream_mode="updates",
        )
    )

    executed_nodes = [node_name for update in updates for node_name in update]
    assert executed_nodes == ["reconciliation"]

    reconciliation_state = updates[0]["reconciliation"]
    assert reconciliation_state["status"] == "matched"
    assert reconciliation_state["recommended_status"] == "matched"
    assert reconciliation_state["needs_review"] is False


@patch("app.agents.orchestrator.run_reconciliation_agent")
def test_reconciliation_graph_low_confidence_runs_review_router(mock_agent):
    mock_agent.return_value = ReconciliationResponse(
        agent_name="reconciliation_agent",
        status="completed",
        confidence_score=0.75,
        rationale="Candidate requires human review.",
        result=ReconciliationResult(
            bank_transaction_id="tx-103",
            matches=[
                ProposedMatchCandidate(
                    journal_entry_id="je-103",
                    match_type="fuzzy",
                    confidence_score=0.75,
                    amount_score=1.0,
                    date_score=0.7,
                    vendor_score=0.6,
                    rationale="Amount matches but other signals are ambiguous.",
                )
            ],
            recommended_status="possible_match_review_required",
        ),
    )

    updates = list(
        reconciliation_graph.stream(
            {
                "bank_transaction": {"id": "tx-103", "amount": 250000.0},
                "candidate_journal_entries": [{"id": "je-103"}],
            },
            stream_mode="updates",
        )
    )

    executed_nodes = [node_name for update in updates for node_name in update]
    assert executed_nodes == ["reconciliation", "review_router"]

    reconciliation_state = updates[0]["reconciliation"]
    assert (
        reconciliation_state["recommended_status"] == "possible_match_review_required"
    )
    assert reconciliation_state["needs_review"] is True
    assert updates[1]["review_router"] == {
        "needs_review": True,
        "warnings": ["Routed to human review queue for manual verification."],
    }


@patch("app.agents.orchestrator.run_reconciliation_agent")
def test_reconciliation_graph_preserves_agent_failure(mock_agent):
    mock_agent.return_value = ReconciliationResponse(
        agent_name="reconciliation_agent",
        status="failed",
        confidence_score=0.0,
        rationale="Provider unavailable.",
        result=ReconciliationResult(
            bank_transaction_id="tx-102",
            matches=[],
            recommended_status="unmatched_review_required",
        ),
    )

    final_state = reconciliation_graph.invoke(
        {
            "bank_transaction": {"id": "tx-102", "amount": 250000.0},
            "candidate_journal_entries": [{"id": "je-102"}],
        }
    )

    assert final_state["status"] == "failed"
    assert final_state["needs_review"] is False
    assert final_state["error"] == "Provider unavailable."
