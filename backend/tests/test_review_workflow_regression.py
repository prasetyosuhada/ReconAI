"""Source evidence -> invalid decision -> correction -> duplicate API regression."""

import copy
from pathlib import Path

import pymupdf
import pytest
from test_review_correction_validation import (
    bookkeeping as bookkeeping_fixture,
)
from test_review_correction_validation import (
    extraction_review as extraction_review_fixture,
)

from app.api.v1 import documents
from app.models.audit import AuditEvent
from app.models.journal import JournalEntry
from app.services.document_extraction import extract_document_content

bookkeeping = bookkeeping_fixture
extraction_review = extraction_review_fixture


def _source(path: Path, kind: str) -> None:
    with pymupdf.open() as pdf:
        for index in range(2):
            page = pdf.new_page(width=200, height=200)
            page.insert_text((20, 40), f"Invoice supplier, page {index + 1}")
            page.insert_text((20, 60), "Subtotal 100 Tax 10 Total 110 IDR")
        if kind == "digital":
            pdf.save(path)
        elif kind == "image":
            path.write_bytes(pdf[0].get_pixmap().tobytes("png"))
        else:
            with pymupdf.open() as scanned:
                for page in pdf:
                    image = page.get_pixmap().tobytes("png")
                    scanned.new_page(width=200, height=200).insert_image(
                        pymupdf.Rect(0, 0, 200, 200), stream=image
                    )
                scanned.save(path)


@pytest.mark.parametrize("kind", ["digital", "scanned", "image", "missing"])
def test_source_review_correction_and_retry(
    client, db_session, tmp_path, monkeypatch, extraction_review, bookkeeping, kind
):
    doc, extraction, review = extraction_review
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(documents, "UPLOAD_STORAGE_DIR", root)
    path = root / ("invoice.png" if kind == "image" else "invoice.pdf")
    doc.mime_type = "image/png" if kind == "image" else "application/pdf"
    doc.original_filename = path.name
    doc.stored_file_path = str(path)
    if kind != "missing":
        _source(path, kind)
        doc.file_size_bytes = path.stat().st_size
    content = extract_document_content(str(path), doc.mime_type)
    metadata = {
        **content.provider_metadata,
        "extraction_method": content.extraction_method.value,
        "warnings": content.warnings,
    }
    extraction.provider_metadata = metadata
    extraction.vendor_name = None
    original_payload = copy.deepcopy(review.original_payload)
    db_session.commit()
    source_url = f"/api/v1/documents/{doc.id}/content"
    review_url = f"/api/v1/review-items/{review.id}"

    evidence = client.get(source_url)
    if kind == "missing":
        assert evidence.status_code == 410
        assert evidence.json()["error"]["code"] == "source_content_unavailable"
        assert str(root) not in evidence.text
    else:
        assert evidence.status_code == 200
        assert evidence.content == path.read_bytes()
        assert evidence.headers["content-type"] == doc.mime_type
        if kind in {"digital", "scanned"}:
            with pymupdf.open(stream=evidence.content, filetype="pdf") as pdf:
                assert pdf.page_count == 2
            assert metadata["source_page_count"] == 2
            assert metadata["extraction_method"] == (
                "pdf_text" if kind == "digital" else "pdf_vision"
            )
            assert metadata["vision_page_numbers"] == (
                [] if kind == "digital" else [1, 2]
            )

    detail = client.get(review_url)
    assert detail.status_code == 200
    assert "stored_file_path" not in detail.json()
    latest = client.get(f"/api/v1/documents/{doc.id}/extractions/latest")
    assert latest.json()["provider_metadata"] == metadata
    for action, body in [
        ("approve", {}),
        ("edit", {"edited_payload": {"vendor_name": " "}}),
    ]:
        invalid = client.post(f"{review_url}/{action}", json=body)
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "extraction_validation_failed"
        assert any(
            error["field"] == "vendor_name"
            for error in invalid.json()["error"]["details"]
        )
        assert client.get(review_url).json()["status"] == "pending"
        assert db_session.query(JournalEntry).count() == 0
        assert db_session.query(AuditEvent).count() == 0
    bookkeeping.assert_not_called()

    correction = {"edited_payload": {"vendor_name": "Verified supplier"}}
    resolved = client.post(f"{review_url}/edit", json=correction)
    assert resolved.status_code == 200
    assert resolved.json()["next_workflow_status"] == "ready_to_post"
    for action in ["approve", "edit", "reject"]:
        retry = client.post(f"{review_url}/{action}", json=correction)
        assert retry.status_code == 409
        assert retry.json()["error"]["code"] == "review_already_resolved"
    bookkeeping.assert_called_once()
    db_session.refresh(extraction)
    db_session.refresh(review)
    assert extraction.vendor_name == "Verified supplier"
    assert extraction.provider_metadata == metadata
    assert float(extraction.confidence_score) == 0.4
    assert review.original_payload == original_payload
    assert db_session.query(JournalEntry).count() == 1
    assert db_session.query(AuditEvent).count() == 2
    assert client.get(source_url).status_code == evidence.status_code
