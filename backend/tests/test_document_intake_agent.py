from unittest.mock import MagicMock, patch

from app.agents.document_intake import run_document_intake_agent
from app.agents.schemas import DocumentExtractionResult, DocumentIntakeResponse


def test_document_intake_agent_empty_text():
    response = run_document_intake_agent(raw_text="")
    assert response.status == "needs_review"
    assert response.confidence_score == 0.0
    assert "no readable text" in response.warnings[0].lower()


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = DocumentIntakeResponse(
        agent_name="document_intake_agent",
        status="completed",
        confidence_score=0.95,
        rationale="Clear vendor and totals extracted.",
        warnings=[],
        result=DocumentExtractionResult(
            document_type="receipt",
            vendor_name="Toko Gramedia",
            transaction_date="2026-07-15",
            currency="IDR",
            subtotal_amount=100000.0,
            tax_amount=11000.0,
            total_amount=111000.0,
            line_items=[],
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_document_intake_agent(
        raw_text="TOKO GRAMEDIA\n15-07-2026\nSubtotal: 100000\nPPN: 11000\nTotal: 111000",
        original_filename="receipt.pdf",
    )

    assert response.status == "completed"
    assert response.confidence_score == 0.95
    assert response.result.vendor_name == "Toko Gramedia"
    assert response.result.total_amount == 111000.0


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_heuristic_math_mismatch(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    dummy_response = DocumentIntakeResponse(
        agent_name="document_intake_agent",
        status="completed",
        confidence_score=0.90,
        rationale="Extracted values.",
        warnings=[],
        result=DocumentExtractionResult(
            document_type="invoice",
            vendor_name="PT Supplier Utama",
            transaction_date="2026-07-10",
            currency="IDR",
            subtotal_amount=100000.0,
            tax_amount=11000.0,
            total_amount=150000.0,  # Math mismatch (100k + 11k != 150k)
            line_items=[],
        ),
    )

    mock_structured_llm.invoke.return_value = dummy_response
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_document_intake_agent(
        raw_text="PT Supplier Utama\nTotal: 150000",
        original_filename="invoice.pdf",
    )

    # Heuristic should lower confidence and flag warning
    assert response.status == "needs_review"
    assert response.confidence_score <= 0.75
    assert any("does not match Total" in w for w in response.warnings)
