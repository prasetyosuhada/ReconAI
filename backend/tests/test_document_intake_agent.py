from unittest.mock import MagicMock, patch

from app.agents.document_intake import run_document_intake_agent
from app.agents.schemas import DocumentExtractionResult, DocumentIntakeResponse
from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)


def test_document_intake_agent_empty_text():
    response = run_document_intake_agent(raw_text="  \n")
    assert response.status == "needs_review"
    assert response.confidence_score == 0.0
    assert "no readable text" in response.warnings[0].lower()


@patch(
    "app.agents.document_intake.get_llm_runtime_metadata",
    return_value=("gemini", "gemini-test"),
)
@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_success(mock_get_llm, mock_runtime_metadata):
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
        raw_text="TOKO GRAMEDIA\n15-07-2026\nTotal: 111000",
        original_filename="receipt.pdf",
    )

    assert response.status == "completed"
    assert response.confidence_score == 0.95
    assert response.result.vendor_name == "Toko Gramedia"
    assert response.result.total_amount == 111000.0
    assert response.llm_provider == "gemini"
    assert response.llm_model == "gemini-test"
    mock_runtime_metadata.assert_called_once_with(mock_llm)


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


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_sends_all_visual_pages_with_page_mime_types(
    mock_get_llm,
):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = DocumentIntakeResponse(
        agent_name="document_intake_agent",
        status="completed",
        confidence_score=0.95,
        rationale="All visual pages were readable.",
        result=DocumentExtractionResult(
            document_type="invoice",
            vendor_name="PT Multi Page",
            transaction_date="2026-09-09",
            currency="IDR",
            total_amount=250000.0,
        ),
    )
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm
    document_content = DocumentContent(
        text="Embedded text from the first PDF page.",
        visual_pages=[
            DocumentVisualPage(
                page_number=2,
                mime_type="image/png",
                image_base64="cGFnZS0y",
                source="rendered_pdf_page",
            ),
            DocumentVisualPage(
                page_number=4,
                mime_type="image/jpeg",
                image_base64="cGFnZS00",
                source="uploaded_image",
            ),
        ],
        extraction_method=DocumentExtractionMethod.PDF_HYBRID,
    )

    response = run_document_intake_agent(
        document_content=document_content,
        original_filename="DO-NOT-INFER-IDR-999.pdf",
        mime_type="application/pdf",
    )

    assert response.status == "completed"
    messages = mock_structured_llm.invoke.call_args.args[0]
    system_content = messages[0].content
    human_content = messages[1].content
    assert "Never use a filename" in system_content
    assert isinstance(human_content, list)
    assert "DO-NOT-INFER-IDR-999.pdf" not in str(human_content)
    assert human_content == [
        {
            "type": "text",
            "text": (
                "Source MIME Type: application/pdf\n"
                "Default Currency: IDR\n\n"
                "--- DOCUMENT TEXT BEGIN ---\n"
                "Embedded text from the first PDF page.\n"
                "--- DOCUMENT TEXT END ---"
            ),
        },
        {
            "type": "text",
            "text": "--- VISUAL PAGE 2 (image/png) ---",
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,cGFnZS0y"},
        },
        {
            "type": "text",
            "text": "--- VISUAL PAGE 4 (image/jpeg) ---",
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,cGFnZS00"},
        },
    ]
