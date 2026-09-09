import base64

import pymupdf
import pytest
from pydantic import ValidationError

from app.schemas.document_content import (
    DocumentContent,
    DocumentExtractionMethod,
    DocumentVisualPage,
)
from app.services.document_extraction import extract_document_content


def _create_pdf(
    file_path,
    page_texts: list[str | None],
    *,
    width: float = 595,
    height: float = 842,
) -> None:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page(width=width, height=height)
        if text:
            page.insert_textbox(
                pymupdf.Rect(72, 72, width - 72, height - 72),
                text,
                fontsize=12,
            )
    document.save(file_path)
    document.close()


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
    extracted_text = "Vendor: Example Supplier\nInvoice total: IDR 125,000"
    _create_pdf(pdf_file, [extracted_text])

    content = extract_document_content(str(pdf_file), "application/pdf")

    assert content.text == extracted_text
    assert content.extraction_method == DocumentExtractionMethod.PDF_TEXT
    assert content.visual_pages == []
    assert content.warnings == []
    assert content.provider_metadata["text_page_numbers"] == [1]
    assert content.provider_metadata["vision_page_numbers"] == []
    assert content.provider_metadata["page_classifications"] == [
        {
            "page_number": 1,
            "content_type": "text",
            "embedded_text_char_count": len(extracted_text),
        }
    ]


def test_extract_document_content_renders_scanned_pdf_page(tmp_path):
    pdf_file = tmp_path / "scanned.pdf"
    _create_pdf(pdf_file, [None])

    content = extract_document_content(str(pdf_file), "application/pdf")

    assert content.extraction_method == DocumentExtractionMethod.PDF_VISION
    assert content.text.startswith("[SCANNED PDF]")
    assert content.warnings == []
    assert len(content.visual_pages) == 1
    visual_page = content.visual_pages[0]
    assert visual_page.page_number == 1
    assert visual_page.mime_type == "image/png"
    assert visual_page.source == "rendered_pdf_page"
    assert visual_page.width_pixels is not None
    assert visual_page.height_pixels is not None
    assert visual_page.render_dpi == 150
    assert base64.b64decode(visual_page.image_base64).startswith(b"\x89PNG")
    assert content.provider_metadata["embedded_text_char_count"] == 0
    assert content.provider_metadata["vision_page_numbers"] == [1]
    assert content.provider_metadata["rendered_page_numbers"] == [1]


def test_extract_document_content_detects_mixed_pdf_per_page(tmp_path):
    pdf_file = tmp_path / "mixed.pdf"
    extracted_text = "Vendor: Example Supplier\nInvoice total: IDR 125,000"
    _create_pdf(pdf_file, [extracted_text, None])

    content = extract_document_content(str(pdf_file), "application/pdf")

    assert content.extraction_method == DocumentExtractionMethod.PDF_HYBRID
    assert content.text == extracted_text
    assert [page.page_number for page in content.visual_pages] == [2]
    assert content.provider_metadata["text_page_numbers"] == [1]
    assert content.provider_metadata["vision_page_numbers"] == [2]
    assert content.provider_metadata["page_classifications"] == [
        {
            "page_number": 1,
            "content_type": "text",
            "embedded_text_char_count": len(extracted_text),
        },
        {
            "page_number": 2,
            "content_type": "scanned",
            "embedded_text_char_count": 0,
        },
    ]


def test_extract_document_content_limits_processed_pdf_pages(tmp_path):
    pdf_file = tmp_path / "long-scanned.pdf"
    _create_pdf(pdf_file, [None, None, None])

    content = extract_document_content(
        str(pdf_file),
        "application/pdf",
        max_pdf_pages=2,
    )

    assert [page.page_number for page in content.visual_pages] == [1, 2]
    assert content.provider_metadata["source_page_count"] == 3
    assert content.provider_metadata["processed_page_count"] == 2
    assert content.provider_metadata["page_limit_applied"] is True
    assert content.warnings == [
        "PDF has 3 pages; only the first 2 pages were processed."
    ]


def test_extract_document_content_limits_rendered_page_resolution(tmp_path):
    pdf_file = tmp_path / "large-page.pdf"
    _create_pdf(pdf_file, [None], width=2000, height=3000)
    max_pixels = 100_000

    content = extract_document_content(
        str(pdf_file),
        "application/pdf",
        pdf_render_dpi=300,
        max_rendered_page_pixels=max_pixels,
    )

    visual_page = content.visual_pages[0]
    assert visual_page.width_pixels * visual_page.height_pixels <= max_pixels
    assert visual_page.render_dpi < 300


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
