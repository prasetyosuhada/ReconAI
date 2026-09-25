"""Task 15.5: invalid human decisions never resolve a review or run bookkeeping."""

import copy
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from app.agents.schemas import BookkeepingOutcome
from app.api.v1.review_items import approve_review_item, edit_review_item
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.schemas.review import ReviewEditRequest
from app.services.review_validation import (
    ExtractionCorrectionError,
    validate_review_extraction,
)


@pytest.fixture
def extraction_review(db_session):
    doc = Document(
        id=uuid.uuid4(),
        original_filename="invoice.pdf",
        stored_file_path="/tmp/invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        document_type="invoice",
        status="extraction_review_required",
    )
    payload = dict(
        document_type="invoice",
        vendor_name="Supplier",
        transaction_date="2026-09-01",
        currency="IDR",
        subtotal_amount=100.0,
        tax_amount=10.0,
        total_amount=110.0,
        line_items=[
            dict(description="Supplies", quantity=1, unit_price=100, amount=100)
        ],
    )
    extraction = DocumentExtraction(
        id=uuid.uuid4(),
        document_id=doc.id,
        **{
            k: v
            for k, v in payload.items()
            if k not in {"document_type", "transaction_date"}
        },
        transaction_date=date(2026, 9, 1),
        status="draft",
        confidence_score=0.4,
        raw_text="Original source text",
        rationale="Uncertain extraction",
        provider_metadata={
            "warnings": ["Blurred source"],
            "risk_flags": ["partial_document_page_limit"],
        },
    )
    item = ReviewItem(
        id=uuid.uuid4(),
        source_id=doc.id,
        source_type="document",
        review_type="extraction",
        status="pending",
        priority="normal",
        title="Review extraction",
        original_payload=payload,
    )
    db_session.add_all([doc, extraction, item])
    db_session.commit()
    return doc, extraction, item


INVALID_CORRECTIONS = [
    ({"vendor_name": " "}, "vendor_name", "missing_vendor_name"),
    ({"vendor_name": None}, "vendor_name", "missing_vendor_name"),
    ({"vendor_name": 12}, "vendor_name", "invalid_vendor_name"),
    ({"transaction_date": None}, "transaction_date", "missing_transaction_date"),
    (
        {"transaction_date": "2026-02-30"},
        "transaction_date",
        "invalid_transaction_date",
    ),
    ({"transaction_date": "2026-9-01"}, "transaction_date", "invalid_transaction_date"),
    (
        {"transaction_date": "2026-09-01T12:00:00"},
        "transaction_date",
        "invalid_transaction_date",
    ),
    ({"currency": "idr"}, "currency", "invalid_currency"),
    ({"currency": ""}, "currency", "invalid_currency"),
    ({"document_type": "unknown"}, "document_type", "unknown_document_type"),
    ({"document_type": "statement"}, "document_type", "invalid_document_type"),
    ({"total_amount": None}, "total_amount", "missing_total_amount"),
    ({"total_amount": 0}, "total_amount", "invalid_total_amount"),
    ({"total_amount": -1}, "total_amount", "invalid_total_amount"),
    ({"total_amount": True}, "total_amount", "invalid_total_amount"),
    ({"tax_amount": -1}, "tax_amount", "invalid_tax_amount"),
    ({"subtotal_amount": "NaN"}, "subtotal_amount", "invalid_subtotal_amount"),
    ({"total_amount": 120}, "tax_amount", "subtotal_tax_total_mismatch"),
    (
        {"line_items": [{"description": "Supplies", "amount": 99}]},
        "line_items",
        "line_item_subtotal_mismatch",
    ),
    (
        {"line_items": [{"description": "Supplies", "quantity": -1}]},
        "line_items",
        "invalid_line_item_amount",
    ),
    (
        {"line_items": [{"description": "Supplies", "unit_price": True}]},
        "line_items.0.unit_price",
        "invalid_line_items",
    ),
    ({"line_items": "invalid"}, "line_items", "invalid_line_items"),
    ({"line_items": [None]}, "line_items.0", "invalid_line_items"),
]


@pytest.mark.parametrize("action", ["approve", "edit"])
@pytest.mark.parametrize("correction,field,code", INVALID_CORRECTIONS)
def test_invalid_decision_returns_field_errors_without_side_effects(
    client,
    db_session,
    extraction_review,
    action,
    correction,
    field,
    code,
):
    doc, extraction, item = extraction_review
    if action == "approve":
        # Exercise original review payload validation when no persisted extraction exists.
        db_session.delete(extraction)
        item.original_payload = {**item.original_payload, **correction}
        if "document_type" in correction:
            doc.document_type = correction["document_type"]
        db_session.commit()
    with patch("app.api.v1.review_items.classify_bookkeeping") as classify:
        response = client.post(
            f"/api/v1/review-items/{item.id}/{action}",
            json={"edited_payload": correction} if action == "edit" else {},
        )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "extraction_validation_failed"
    assert any(
        detail["field"] == field and detail["code"] == code
        for detail in error["details"]
    )
    classify.assert_not_called()
    db_session.refresh(item)
    db_session.refresh(doc)
    assert item.status == "pending"
    assert item.edited_payload is None
    assert item.resolved_at is None and item.resolved_by is None
    assert doc.status == "extraction_review_required"
    assert db_session.query(JournalEntry).count() == 0
    assert db_session.query(AuditEvent).count() == 0
    if action == "edit":
        db_session.refresh(extraction)
        assert extraction.status == "draft"
        assert extraction.vendor_name == "Supplier"
        assert float(extraction.total_amount) == 110


@pytest.mark.parametrize("action", ["approve", "edit"])
def test_invalid_persisted_extraction_is_rechecked_before_mutation(
    db_session,
    extraction_review,
    action,
):
    doc, extraction, item = extraction_review
    extraction.vendor_name = None
    db_session.commit()
    with patch("app.api.v1.review_items.classify_bookkeeping") as classify:
        with pytest.raises(ExtractionCorrectionError):
            if action == "approve":
                approve_review_item(str(item.id), db=db_session)
            else:
                edit_review_item(
                    str(item.id), ReviewEditRequest(edited_payload={}), db=db_session
                )
    # Inspect the same session: rollback must not be what protects the pending state.
    assert item.status == "pending" and item.resolved_at is None
    assert extraction.vendor_name is None and extraction.status == "draft"
    assert not db_session.dirty and not db_session.new
    classify.assert_not_called()


@pytest.fixture
def bookkeeping(db_session):
    db_session.add_all(
        [
            ChartOfAccount(
                account_code="5100",
                account_name="Supplies",
                account_type="expense",
                normal_balance="debit",
                is_active=True,
            ),
            ChartOfAccount(
                account_code="2000",
                account_name="Payable",
                account_type="liability",
                normal_balance="credit",
                is_active=True,
            ),
        ]
    )
    db_session.commit()
    with patch("app.api.v1.review_items.classify_bookkeeping") as classify:
        classify.return_value = BookkeepingOutcome(
            entry_date="2026-09-01",
            entry_description="Purchase",
            status="ready_to_post",
            confidence_score=0.95,
            is_balanced=True,
            total_debit=110,
            total_credit=110,
            journal_lines=[
                dict(
                    account_code="5100",
                    account_name="Supplies",
                    debit_amount=110,
                    credit_amount=0,
                ),
                dict(
                    account_code="2000",
                    account_name="Payable",
                    debit_amount=0,
                    credit_amount=110,
                ),
            ],
        )
        yield classify


@pytest.mark.parametrize("action", ["approve", "edit"])
def test_valid_decision_uses_persisted_fields_and_preserves_evidence(
    client,
    db_session,
    extraction_review,
    bookkeeping,
    action,
):
    doc, extraction, item = extraction_review
    item.original_payload = {
        **item.original_payload,
        "vendor_name": "Stale vendor",
        "total_amount": 999,
    }
    original_payload = copy.deepcopy(item.original_payload)
    metadata = copy.deepcopy(extraction.provider_metadata)
    db_session.commit()
    correction = {
        "vendor_name": "Corrected vendor",
        "confidence_score": 1,
        "raw_text": "Forged",
        "provider_metadata": {},
        "risk_flags": [],
        "rationale": "Forged",
        "payment_status": "paid",
        "lines": [],
        "status": "posted",
        "line_items": [
            {"description": "Supplies", "amount": 100, "account_code": "1010"}
        ],
    }
    response = client.post(
        f"/api/v1/review-items/{item.id}/{action}",
        json={"edited_payload": correction, "resolution_note": "Reviewed"}
        if action == "edit"
        else {},
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_workflow_status"] == "ready_to_post"
    bookkeeping.assert_called_once()
    data = bookkeeping.call_args.kwargs["extraction_data"]
    assert data["total_amount"] == 110
    assert data["vendor_name"] == (
        "Corrected vendor" if action == "edit" else "Supplier"
    )
    db_session.refresh(extraction)
    db_session.refresh(item)
    assert extraction.provider_metadata == metadata
    assert float(extraction.confidence_score) == 0.4
    assert extraction.raw_text == "Original source text"
    assert extraction.rationale == "Uncertain extraction"
    assert item.original_payload == original_payload
    journal = db_session.query(JournalEntry).one()
    assert journal.status != "posted" and len(journal.lines) == 2
    if action == "edit":
        assert item.edited_payload == {
            "vendor_name": "Corrected vendor",
            "line_items": [{"description": "Supplies", "amount": 100}],
        }
        audit = (
            db_session.query(AuditEvent)
            .filter_by(event_type="review_item_edited")
            .one()
        )
        assert audit.input_snapshot["edited_payload"] == item.edited_payload


def test_latest_extraction_wins_over_older_valid_data(
    client, db_session, extraction_review
):
    doc, extraction, item = extraction_review
    extraction.created_at = datetime.now(UTC) - timedelta(days=1)
    latest = DocumentExtraction(
        document_id=doc.id, vendor_name=None, status="draft", currency="IDR"
    )
    db_session.add(latest)
    db_session.commit()
    with patch("app.api.v1.review_items.classify_bookkeeping") as classify:
        response = client.post(f"/api/v1/review-items/{item.id}/approve")
    assert response.status_code == 422
    assert "missing_vendor_name" in response.json()["error"]["risk_flags"]
    classify.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_are_rejected(extraction_review, value):
    payload = {**extraction_review[2].original_payload, "total_amount": value}
    with pytest.raises(ExtractionCorrectionError) as error:
        validate_review_extraction(payload)
    assert "invalid_total_amount" in error.value.validation.risk_flags


@pytest.mark.parametrize("difference,valid", [(0.05, True), (0.06, False)])
def test_amount_tolerance_uses_decimal_arithmetic(extraction_review, difference, valid):
    payload = {
        **extraction_review[2].original_payload,
        "total_amount": 110 + difference,
    }
    if valid:
        validate_review_extraction(payload)
    else:
        with pytest.raises(ExtractionCorrectionError):
            validate_review_extraction(payload)


def test_missing_currency_is_not_defaulted_to_idr(extraction_review):
    payload = dict(extraction_review[2].original_payload)
    del payload["currency"]
    with pytest.raises(ExtractionCorrectionError) as error:
        validate_review_extraction(payload)
    assert "invalid_currency" in error.value.validation.risk_flags


@pytest.mark.parametrize("wrapper", ["items", "line_items", "unexpected"])
def test_legacy_line_item_wrapper_is_validated(
    client,
    db_session,
    extraction_review,
    bookkeeping,
    wrapper,
):
    doc, extraction, item = extraction_review
    extraction.line_items = {wrapper: extraction.line_items}
    db_session.commit()
    response = client.post(f"/api/v1/review-items/{item.id}/approve")
    if wrapper == "unexpected":
        assert response.status_code == 422
        assert "invalid_line_items" in response.json()["error"]["risk_flags"]
        bookkeeping.assert_not_called()
    else:
        assert response.status_code == 200, response.text
        assert (
            bookkeeping.call_args.kwargs["extraction_data"]["line_items"][0]["amount"]
            == 100
        )


def test_failed_approval_can_be_corrected_and_continued(
    client,
    db_session,
    extraction_review,
    bookkeeping,
):
    doc, extraction, item = extraction_review
    extraction.vendor_name = None
    db_session.commit()
    rejected = client.post(f"/api/v1/review-items/{item.id}/approve")
    assert rejected.status_code == 422
    bookkeeping.assert_not_called()
    corrected = client.post(
        f"/api/v1/review-items/{item.id}/edit",
        json={"edited_payload": {"vendor_name": "Verified supplier"}},
    )
    assert corrected.status_code == 200, corrected.text
    bookkeeping.assert_called_once()
    db_session.refresh(item)
    db_session.refresh(extraction)
    assert item.status == "edited"
    assert extraction.vendor_name == "Verified supplier"
    assert db_session.query(JournalEntry).count() == 1
