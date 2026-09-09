import base64
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)
from app.services.document_extraction import extract_document_content


def test_extract_document_content_returns_missing_file_result(tmp_path):
    missing_file = tmp_path / "missing.pdf"

    content = extract_document_content(str(missing_file), "application/pdf")

    assert content == DocumentContent(
        extraction_method=DocumentExtractionMethod.FILE_NOT_FOUND,
        warnings=["Document file was not found at the stored path."],
        provider_metadata={"source_mime_type": "application/pdf"},
    )


def test_extract_document_content_returns_pdf_text_result(tmp_path):
    pdf_file = tmp_path / "invoice.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 placeholder")
    extracted_text = "Vendor: Example Supplier\nInvoice total: IDR 125,000"

    with patch(
        "app.services.document_extraction.extract_text_from_pdf",
        return_value=extracted_text,
    ):
        content = extract_document_content(str(pdf_file), "application/pdf")

    assert content.text == extracted_text
    assert content.extraction_method == DocumentExtractionMethod.PDF_TEXT
    assert content.visual_pages == []
    assert content.warnings == []
    assert content.provider_metadata == {
        "source_mime_type": "application/pdf",
        "source_suffix": ".pdf",
        "file_size_bytes": pdf_file.stat().st_size,
        "text_extractor": "pypdf",
        "embedded_text_char_count": len(extracted_text),
    }


def test_extract_document_content_returns_structured_scanned_pdf_fallback(tmp_path):
    pdf_file = tmp_path / "scanned.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 placeholder")

    with patch(
        "app.services.document_extraction.extract_text_from_pdf", return_value=""
    ):
        content = extract_document_content(str(pdf_file), "application/pdf")

    assert content.extraction_method == DocumentExtractionMethod.SCANNED_PDF_FALLBACK
    assert content.text.startswith("[SCANNED PDF]")
    assert content.visual_pages == []
    assert content.warnings == [
        "PDF contains insufficient embedded text; scanned-page rendering is not "
        "yet available."
    ]
    assert content.provider_metadata["embedded_text_char_count"] == 0


@pytest.mark.parametrize(
    ("suffix", "mime_type"),
    [(".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp")],
)
def test_extract_document_content_returns_visual_page_for_image(
    tmp_path, suffix, mime_type
):
    image_file = tmp_path / f"receipt{suffix}"
    image_bytes = b"test-image-bytes"
    image_file.write_bytes(image_bytes)

    content = extract_document_content(str(image_file), mime_type)

    assert content.extraction_method == DocumentExtractionMethod.IMAGE_VISION
    assert content.primary_visual_page is content.visual_pages[0]
    assert content.primary_visual_page.page_number == 1
    assert content.primary_visual_page.mime_type == mime_type
    assert content.primary_visual_page.source == "uploaded_image"
    assert base64.b64decode(content.primary_visual_page.image_base64) == image_bytes
    assert content.provider_metadata["visual_page_count"] == 1


def test_extract_document_content_returns_unsupported_result(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a supported financial document")

    content = extract_document_content(str(text_file), "text/plain")

    assert content.extraction_method == DocumentExtractionMethod.UNSUPPORTED
    assert content.text == ""
    assert content.visual_pages == []
    assert content.warnings == [
        "Document type is not supported for content extraction."
    ]


def test_visual_page_requires_valid_page_number_and_content():
    with pytest.raises(ValidationError):
        DocumentVisualPage(
            page_number=0,
            mime_type="image/png",
            image_base64="",
            source="rendered_pdf_page",
        )
