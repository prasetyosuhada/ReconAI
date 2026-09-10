"""Task 14.6 extraction matrix across unit, integration, and regression layers."""

import base64
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf
import pytest
from pypdf import PdfWriter

from app.agents.document_intake import run_document_intake_agent
from app.agents.orchestrator import document_processing_graph
from app.agents.schemas import DocumentExtractionResult, DocumentIntakeResponse
from app.models.audit import AuditEvent
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.schemas.document_content import DocumentExtractionMethod
from app.services.document_extraction import (
    MAX_PDF_PAGES,
    MAX_RENDERED_PAGE_PIXELS,
    extract_document_content,
)
from app.services.document_processing import process_document_background
from app.services.extraction_validation import validate_document_content


def _low_quality_png_bytes() -> bytes:
    """Create a tiny low-detail PNG representing an unreadable/blurred upload."""
    width = 16
    height = 8
    samples = bytearray()
    for x in range(width * height):
        shade = 150 + (x % width) * 3
        samples.extend((shade, shade, shade))
    pixmap = pymupdf.Pixmap(
        pymupdf.csRGB,
        width,
        height,
        bytes(samples),
        False,
    )
    return pixmap.tobytes("png")


def _create_pdf(path: Path, pages: list[str | bytes]) -> None:
    """Create text, scanned, or mixed PDF fixtures without external files."""
    document = pymupdf.open()
    for content in pages:
        page = document.new_page(width=240, height=320)
        if isinstance(content, str):
            page.insert_textbox(
                pymupdf.Rect(24, 24, 216, 296),
                content,
                fontsize=10,
            )
        else:
            page.insert_image(
                pymupdf.Rect(24, 24, 216, 296),
                stream=content,
            )
    document.save(path)
    document.close()


def _create_encrypted_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=240, height=320)
    writer.encrypt("test-password")
    with path.open("wb") as file:
        writer.write(file)


def _valid_intake_response(
    *,
    status: str = "completed",
    confidence_score: float = 0.95,
) -> DocumentIntakeResponse:
    return DocumentIntakeResponse(
        status=status,
        confidence_score=confidence_score,
        rationale="Document fields were evaluated from the supplied content.",
        result=DocumentExtractionResult(
            document_type="invoice",
            vendor_name="PT Matrix Supplier",
            transaction_date="2026-09-10",
            currency="IDR",
            subtotal_amount=100_000.0,
            tax_amount=11_000.0,
            total_amount=111_000.0,
        ),
    )


@pytest.mark.parametrize(
    ("page_contents", "expected_method", "text_pages", "vision_pages"),
    [
        pytest.param(
            [
                "Digital invoice header and vendor details on page one.",
                "Digital invoice totals and payment details on page two.",
            ],
            DocumentExtractionMethod.PDF_TEXT,
            [1, 2],
            [],
            id="digital-multi-page-pdf",
        ),
        pytest.param(
            [_low_quality_png_bytes(), _low_quality_png_bytes()],
            DocumentExtractionMethod.PDF_VISION,
            [],
            [1, 2],
            id="scanned-multi-page-pdf",
        ),
        pytest.param(
            [
                "Mixed invoice embedded text and vendor details on page one.",
                _low_quality_png_bytes(),
                "Mixed invoice embedded totals and payment details on page three.",
            ],
            DocumentExtractionMethod.PDF_HYBRID,
            [1, 3],
            [2],
            id="mixed-multi-page-pdf",
        ),
    ],
)
def test_pdf_extraction_unit_matrix_preserves_page_classification(
    tmp_path,
    page_contents,
    expected_method,
    text_pages,
    vision_pages,
):
    pdf_path = tmp_path / "matrix.pdf"
    _create_pdf(pdf_path, page_contents)

    content = extract_document_content(str(pdf_path), "application/pdf")

    assert content.extraction_method == expected_method
    assert content.provider_metadata["text_page_numbers"] == text_pages
    assert content.provider_metadata["vision_page_numbers"] == vision_pages
    assert [page.page_number for page in content.visual_pages] == vision_pages
    assert all(page.mime_type == "image/png" for page in content.visual_pages)
    assert content.provider_metadata["processed_page_count"] == len(page_contents)
    assert validate_document_content(content).can_process is True


def test_image_extraction_regression_uses_actual_bytes_and_mime(tmp_path):
    image_path = tmp_path / "blurry-receipt.png"
    image_bytes = _low_quality_png_bytes()
    image_path.write_bytes(image_bytes)

    content = extract_document_content(str(image_path), "image/png")

    assert content.extraction_method == DocumentExtractionMethod.IMAGE_VISION
    assert content.text == ""
    assert len(content.visual_pages) == 1
    assert content.visual_pages[0].mime_type == "image/png"
    assert base64.b64decode(content.visual_pages[0].image_base64) == image_bytes


@pytest.mark.parametrize("file_kind", ["corrupt", "encrypted"])
def test_invalid_pdf_unit_matrix_fails_safely(tmp_path, file_kind):
    pdf_path = tmp_path / f"{file_kind}.pdf"
    if file_kind == "encrypted":
        _create_encrypted_pdf(pdf_path)
    else:
        pdf_path.write_bytes(b"%PDF-1.7\ncorrupt-and-incomplete")

    content = extract_document_content(str(pdf_path), "application/pdf")
    validation = validate_document_content(content)

    assert content.extraction_method == DocumentExtractionMethod.SCANNED_PDF_FALLBACK
    assert content.text == ""
    assert content.visual_pages == []
    assert content.warnings == [
        "PDF page detection failed before content could be extracted."
    ]
    assert validation.can_process is False
    assert validation.needs_review is True
    assert validation.risk_flags == ["unreadable_document_content"]


def test_default_processing_limits_are_enforced_regression(tmp_path):
    pdf_path = tmp_path / "oversized-document.pdf"
    _create_pdf(
        pdf_path,
        [
            f"Readable digital invoice page {number} with sufficient text content."
            for number in range(1, MAX_PDF_PAGES + 2)
        ],
    )

    content = extract_document_content(str(pdf_path), "application/pdf")
    validation = validate_document_content(content)

    assert content.provider_metadata["source_page_count"] == MAX_PDF_PAGES + 1
    assert content.provider_metadata["processed_page_count"] == MAX_PDF_PAGES
    assert content.provider_metadata["page_limit_applied"] is True
    assert content.provider_metadata["max_rendered_page_pixels"] == (
        MAX_RENDERED_PAGE_PIXELS
    )
    assert validation.needs_review is True
    assert "partial_document_page_limit" in validation.risk_flags


@patch("app.agents.document_intake.get_llm")
def test_mixed_pdf_integration_sends_rendered_pages_in_order(mock_get_llm, tmp_path):
    pdf_path = tmp_path / "mixed-integration.pdf"
    _create_pdf(
        pdf_path,
        [
            "Embedded invoice vendor and date content from the first PDF page.",
            _low_quality_png_bytes(),
            _low_quality_png_bytes(),
        ],
    )
    document_content = extract_document_content(str(pdf_path), "application/pdf")
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = _valid_intake_response()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    response = run_document_intake_agent(
        document_content=document_content,
        original_filename="DO-NOT-INFER-IDR-999.pdf",
        mime_type="application/pdf",
    )

    assert response.status == "completed"
    human_content = mock_structured_llm.invoke.call_args.args[0][1].content
    assert isinstance(human_content, list)
    assert "DO-NOT-INFER-IDR-999.pdf" not in str(human_content)
    visual_labels = [
        block["text"]
        for block in human_content
        if block["type"] == "text" and "VISUAL PAGE" in block["text"]
    ]
    assert visual_labels == [
        "--- VISUAL PAGE 2 (image/png) ---",
        "--- VISUAL PAGE 3 (image/png) ---",
    ]
    image_urls = [
        block["image_url"]["url"]
        for block in human_content
        if block["type"] == "image_url"
    ]
    assert len(image_urls) == 2
    assert all(url.startswith("data:image/png;base64,") for url in image_urls)


@patch("app.agents.document_intake.get_llm")
def test_blurry_image_integration_routes_low_confidence_to_review(
    mock_get_llm,
    tmp_path,
):
    image_path = tmp_path / "blurry-receipt.png"
    image_path.write_bytes(_low_quality_png_bytes())
    document_content = extract_document_content(str(image_path), "image/png")
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = _valid_intake_response(
        status="needs_review",
        confidence_score=0.42,
    )
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    updates = list(
        document_processing_graph.stream(
            {
                "document_content": document_content,
                "raw_text": None,
                "original_filename": image_path.name,
                "mime_type": "image/png",
                "chart_of_accounts": [],
            },
            stream_mode="updates",
        )
    )

    assert [node_name for update in updates for node_name in update] == [
        "document_intake",
        "review_router",
    ]
    intake_state = updates[0]["document_intake"]
    assert intake_state["status"] == "extraction_review_required"
    assert intake_state["needs_review"] is True
    assert intake_state["confidence_score"] == 0.42


@pytest.mark.parametrize("file_kind", ["corrupt", "encrypted"])
@patch("app.services.document_processing.publish_document_progress")
@patch("app.services.document_processing.SessionLocal")
def test_invalid_pdf_pipeline_regression_persists_human_review(
    mock_session_class,
    mock_publish_progress,
    file_kind,
    db_session,
    tmp_path,
):
    mock_session_class.return_value = db_session
    pdf_path = tmp_path / f"{file_kind}-pipeline.pdf"
    if file_kind == "encrypted":
        _create_encrypted_pdf(pdf_path)
    else:
        pdf_path.write_bytes(b"%PDF-1.7\ncorrupt-and-incomplete")

    document_id = uuid.uuid4()
    db_session.add(
        Document(
            id=document_id,
            original_filename=pdf_path.name,
            stored_file_path=str(pdf_path),
            mime_type="application/pdf",
            file_size_bytes=pdf_path.stat().st_size,
            document_type="unknown",
            status="uploaded",
        )
    )
    db_session.commit()

    with patch("app.agents.document_intake.get_llm") as mock_get_llm:
        process_document_background(document_id=str(document_id))

    mock_get_llm.assert_not_called()
    document = db_session.query(Document).filter(Document.id == document_id).one()
    extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == document_id)
        .one()
    )
    review = (
        db_session.query(ReviewItem)
        .filter(
            ReviewItem.source_id == document_id,
            ReviewItem.review_type == "extraction",
            ReviewItem.status == "pending",
        )
        .one()
    )
    audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.source_id == document_id,
            AuditEvent.event_type == "extraction_completed",
        )
        .one()
    )

    assert document.status == "extraction_review_required"
    assert extraction.status == "draft"
    assert extraction.provider_metadata["extraction_method"] == ("scanned_pdf_fallback")
    assert extraction.provider_metadata["risk_flags"] == ["unreadable_document_content"]
    assert review.original_payload["risk_flags"] == ["unreadable_document_content"]
    assert audit.output_snapshot["needs_review"] is True
    assert (
        db_session.query(JournalEntry)
        .filter(JournalEntry.document_id == document_id)
        .count()
        == 0
    )
    assert mock_publish_progress.call_count > 0
