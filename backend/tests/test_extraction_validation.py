from unittest.mock import MagicMock, patch

from app.agents.document_intake import run_document_intake_agent
from app.agents.schemas import (
    DocumentExtractionResult,
    DocumentIntakeResponse,
    ExtractedLineItem,
)
from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)
from app.services.extraction_validation import (
    validate_document_content,
    validate_extraction_result,
)


def test_validate_extraction_result_accepts_complete_consistent_fields():
    result = DocumentExtractionResult(
        document_type="invoice",
        vendor_name="PT Valid Supplier",
        transaction_date="2026-09-09",
        currency="IDR",
        subtotal_amount=100000.0,
        tax_amount=11000.0,
        total_amount=111000.0,
        line_items=[
            ExtractedLineItem(description="Paper", amount=60000.0),
            ExtractedLineItem(description="Ink", amount=40000.0),
        ],
    )

    validation = validate_extraction_result(result)

    assert validation.is_valid is True
    assert validation.warnings == []
    assert validation.low_confidence_fields == []
    assert validation.risk_flags == []
    assert validation.confidence_cap is None


def test_validate_extraction_result_rejects_missing_or_invalid_essential_fields():
    result = DocumentExtractionResult(
        document_type="unknown",
        vendor_name=" ",
        transaction_date="2026-02-30",
        currency="idr",
        total_amount=-100.0,
    )

    validation = validate_extraction_result(result)

    assert validation.is_valid is False
    assert set(validation.risk_flags) == {
        "unknown_document_type",
        "missing_vendor_name",
        "invalid_transaction_date",
        "invalid_currency",
        "invalid_total_amount",
    }
    assert set(validation.low_confidence_fields) == {
        "document_type",
        "vendor_name",
        "transaction_date",
        "currency",
        "total_amount",
    }
    assert validation.confidence_cap == 0.70


def test_validate_extraction_result_rejects_inconsistent_amounts():
    result = DocumentExtractionResult(
        document_type="receipt",
        vendor_name="Toko Nominal",
        transaction_date="2026-09-09",
        currency="IDR",
        subtotal_amount=100000.0,
        tax_amount=11000.0,
        total_amount=150000.0,
        line_items=[
            ExtractedLineItem(description="Paper", amount=40000.0),
            ExtractedLineItem(description="Ink", amount=30000.0),
        ],
    )

    validation = validate_extraction_result(result)

    assert validation.is_valid is False
    assert "subtotal_tax_total_mismatch" in validation.risk_flags
    assert "line_item_subtotal_mismatch" in validation.risk_flags
    assert set(validation.low_confidence_fields) == {"tax_amount", "line_items"}
    assert validation.confidence_cap == 0.75


def test_validate_document_content_flags_partial_visual_processing():
    content = DocumentContent(
        text="Embedded document text is still available.",
        visual_pages=[
            DocumentVisualPage(
                page_number=2,
                mime_type="image/png",
                image_base64="cGFnZS0y",
                source="rendered_pdf_page",
            )
        ],
        extraction_method=DocumentExtractionMethod.PDF_HYBRID,
        provider_metadata={
            "page_limit_applied": True,
            "vision_page_numbers": [2, 3],
        },
    )

    validation = validate_document_content(content)

    assert validation.can_process is True
    assert validation.needs_review is True
    assert set(validation.risk_flags) == {
        "partial_document_page_limit",
        "unrendered_visual_pages",
    }
    assert validation.confidence_cap == 0.70


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_does_not_invoke_llm_for_unreadable_content(
    mock_get_llm,
):
    content = DocumentContent(
        extraction_method=DocumentExtractionMethod.SCANNED_PDF_FALLBACK,
        warnings=["PDF page detection failed before content could be extracted."],
    )

    response = run_document_intake_agent(document_content=content)

    mock_get_llm.assert_not_called()
    assert response.status == "needs_review"
    assert response.confidence_score == 0.0
    assert "unreadable_document_content" in response.risk_flags
    assert "total_amount" in response.low_confidence_fields


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_forces_partial_content_to_review(mock_get_llm):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = _valid_intake_response()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm
    content = DocumentContent(
        text="Readable content from the first ten pages.",
        extraction_method=DocumentExtractionMethod.PDF_TEXT,
        provider_metadata={"page_limit_applied": True},
    )

    response = run_document_intake_agent(document_content=content)

    assert response.status == "needs_review"
    assert response.confidence_score == 0.70
    assert "partial_document_page_limit" in response.risk_flags


@patch("app.agents.document_intake.get_llm")
def test_document_intake_agent_routes_model_reported_unreadable_to_review(
    mock_get_llm,
):
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = DocumentIntakeResponse(
        status="failed",
        confidence_score=0.1,
        rationale="Visual document is unreadable.",
        result=DocumentExtractionResult(),
    )
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_document_intake_agent(raw_text="Unreadable OCR fragments")

    assert response.status == "needs_review"
    assert "model_reported_unreadable_document" in response.risk_flags


def _valid_intake_response() -> DocumentIntakeResponse:
    return DocumentIntakeResponse(
        status="completed",
        confidence_score=0.95,
        rationale="Visible fields are complete and consistent.",
        result=DocumentExtractionResult(
            document_type="invoice",
            vendor_name="PT Valid Supplier",
            transaction_date="2026-09-09",
            currency="IDR",
            subtotal_amount=100000.0,
            tax_amount=11000.0,
            total_amount=111000.0,
        ),
    )
