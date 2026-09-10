from unittest.mock import MagicMock

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.llm import get_llm_runtime_metadata
from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)
from app.services.document_processing import _build_extraction_provider_metadata


def test_get_llm_runtime_metadata_normalizes_supported_providers():
    gemini = MagicMock(spec=ChatGoogleGenerativeAI)
    gemini.model = "gemini-test"
    openai = MagicMock(spec=ChatOpenAI)
    openai.model_name = "gpt-test"

    assert get_llm_runtime_metadata(gemini) == ("gemini", "gemini-test")
    assert get_llm_runtime_metadata(openai) == ("openai", "gpt-test")
    assert get_llm_runtime_metadata(MagicMock()) == (None, None)


def test_build_extraction_provider_metadata_preserves_content_observability():
    content = DocumentContent(
        text="Embedded first-page text.",
        visual_pages=[
            DocumentVisualPage(
                page_number=2,
                mime_type="image/png",
                image_base64="cGFnZS0y",
                source="rendered_pdf_page",
            ),
            DocumentVisualPage(
                page_number=3,
                mime_type="image/jpeg",
                image_base64="cGFnZS0z",
                source="uploaded_image",
            ),
        ],
        extraction_method=DocumentExtractionMethod.PDF_HYBRID,
        warnings=["Page warning."],
        provider_metadata={
            "source_page_count": 3,
            "text_page_numbers": [1],
            "vision_page_numbers": [2, 3],
        },
    )

    metadata = _build_extraction_provider_metadata(
        document_content=content,
        content_extraction_duration_ms=25.0,
        intake_processing_duration_ms=125.5,
        llm_provider="gemini",
        llm_model="gemini-test",
        workflow_warnings=["Page warning.", "Validation warning."],
        low_confidence_fields=["tax_amount"],
        risk_flags=["subtotal_tax_total_mismatch"],
    )

    assert metadata["source_page_count"] == 3
    assert metadata["extraction_method"] == "pdf_hybrid"
    assert metadata["vision_processed_page_numbers"] == [2, 3]
    assert metadata["vision_page_mime_types"] == {
        "2": "image/png",
        "3": "image/jpeg",
    }
    assert metadata["llm_provider"] == "gemini"
    assert metadata["llm_model"] == "gemini-test"
    assert metadata["durations_ms"] == {
        "content_extraction": 25.0,
        "document_intake": 125.5,
        "total": 150.5,
    }
    assert metadata["warnings"] == ["Page warning.", "Validation warning."]
    assert metadata["low_confidence_fields"] == ["tax_amount"]
    assert metadata["risk_flags"] == ["subtotal_tax_total_mismatch"]
