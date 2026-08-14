import uuid
from datetime import date
from unittest.mock import patch

from app.models.audit import AuditEvent
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem


def test_list_review_items_empty(client):
    response = client.get("/api/v1/review-items")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_list_review_items_filtering(client, db_session):
    item1 = ReviewItem(
        id=uuid.uuid4(),
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=uuid.uuid4(),
        title="Review Item Pending",
        summary="Low confidence score",
    )
    item2 = ReviewItem(
        id=uuid.uuid4(),
        review_type="extraction",
        status="approved",
        priority="normal",
        source_type="document",
        source_id=uuid.uuid4(),
        title="Review Item Approved",
        summary="Approved by human",
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    # Filter status=pending
    response = client.get("/api/v1/review-items?status=pending")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Review Item Pending"

    # Filter review_type=extraction
    response = client.get("/api/v1/review-items?review_type=extraction")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Review Item Approved"


def test_get_review_item_detail_success(client, db_session):
    item_id = uuid.uuid4()
    source_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=source_id,
        title="Review Bank Account",
        summary="Bank account used",
        suggested_action="Review lines",
        original_payload={"vendor_name": "Gramedia", "total": 150000},
    )
    db_session.add(item)
    db_session.commit()

    response = client.get(f"/api/v1/review-items/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(item_id)
    assert data["title"] == "Review Bank Account"
    assert data["original_payload"]["vendor_name"] == "Gramedia"


def test_get_review_item_detail_not_found(client):
    random_uuid = uuid.uuid4()
    response = client.get(f"/api/v1/review-items/{random_uuid}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_review_item_detail_invalid_uuid(client):
    response = client.get("/api/v1/review-items/invalid-uuid-string")
    assert response.status_code == 400
    assert "Invalid review item UUID format" in response.json()["detail"]


def test_approve_review_item_success(client, db_session):
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="inv_001.pdf",
        stored_file_path="/tmp/inv_001.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        status="uploaded",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        document_id=doc_id,
        entry_date=date(2026, 8, 1),
        description="Test Entry",
        status="review_required",
    )

    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=doc_id,
        title="Review Journal Entry",
    )
    db_session.add_all([doc, je, item])
    db_session.commit()

    # Add lines via accounting helper or direct ORM
    from app.models.coa import ChartOfAccount

    coa1 = ChartOfAccount(
        id=uuid.uuid4(),
        account_code="5100",
        account_name="Supplies",
        account_type="expense",
        normal_balance="debit",
    )
    coa2 = ChartOfAccount(
        id=uuid.uuid4(),
        account_code="1010",
        account_name="Bank",
        account_type="asset",
        normal_balance="debit",
        is_sensitive=True,
    )
    db_session.add_all([coa1, coa2])
    db_session.flush()

    line1 = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=coa1.id,
        line_number=1,
        debit_amount=50000.0,
        credit_amount=0.0,
    )
    line2 = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=coa2.id,
        line_number=2,
        debit_amount=0.0,
        credit_amount=50000.0,
    )
    db_session.add_all([line1, line2])
    db_session.commit()

    response = client.post(
        f"/api/v1/review-items/{item_id}/approve",
        json={"resolution_note": "Looks good, approved!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["next_workflow_status"] == "posted"

    # Verify JournalEntry is posted
    db_session.refresh(je)
    assert je.status == "posted"

    # Verify AuditEvent created
    audit = db_session.query(AuditEvent).filter(AuditEvent.source_id == item_id).first()
    assert audit is not None
    assert audit.event_type == "review_item_approved"


def test_edit_review_item_success(client, db_session):
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="inv_002.pdf",
        stored_file_path="/tmp/inv_002.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        status="uploaded",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        document_id=doc_id,
        entry_date=date(2026, 8, 1),
        description="Test Entry",
        status="review_required",
    )
    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=doc_id,
        title="Review Journal Entry",
    )
    db_session.add_all([doc, je, item])
    db_session.commit()

    edited_payload = {
        "lines": [
            {
                "account_code": "5100",
                "account_name": "Supplies Expense",
                "debit_amount": 75000.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "2000",
                "account_name": "Accounts Payable",
                "debit_amount": 0.0,
                "credit_amount": 75000.0,
            },
        ]
    }

    response = client.post(
        f"/api/v1/review-items/{item_id}/edit",
        json={
            "edited_payload": edited_payload,
            "resolution_note": "Adjusted amount to 75000",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "edited"
    assert data["next_workflow_status"] == "posted"

    # Verify lines replaced and entry posted
    db_session.refresh(je)
    assert je.status == "posted"
    assert len(je.lines) == 2


@patch("app.api.v1.review_items.bookkeeping_node")
def test_edit_extraction_review_continues_to_bookkeeping(
    mock_bookkeeping_node, client, db_session
):
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="blurred_tax_invoice.pdf",
        stored_file_path="/tmp/blurred_tax_invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        document_type="invoice",
        status="extraction_review_required",
    )
    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="extraction",
        status="pending",
        priority="normal",
        source_type="document",
        source_id=doc_id,
        title="Review Extracted Tax",
        original_payload={
            "vendor_name": "PT Blur",
            "transaction_date": "2026-08-01",
            "subtotal_amount": 100000.0,
            "tax_amount": None,
            "total_amount": 111000.0,
            "currency": "IDR",
            "line_items": [],
            "raw_text": "tax value is blurry",
        },
    )
    db_session.add_all([doc, item])
    db_session.commit()

    mock_bookkeeping_node.return_value = {
        "document_id": str(doc_id),
        "vendor_name": "PT Blur",
        "transaction_date": "2026-08-01",
        "entry_date": "2026-08-01",
        "entry_description": "Purchase from PT Blur",
        "journal_lines": [
            {
                "account_code": "5100",
                "account_name": "Supplies Expense",
                "debit_amount": 111000.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "2000",
                "account_name": "Accounts Payable",
                "debit_amount": 0.0,
                "credit_amount": 111000.0,
            },
        ],
        "is_balanced": True,
        "risk_flags": [],
        "confidence_score": 0.91,
        "rationale": "Human-reviewed extraction is bookkept.",
        "status": "ready_to_post",
        "needs_review": False,
    }

    response = client.post(
        f"/api/v1/review-items/{item_id}/edit",
        json={
            "edited_payload": {"tax_amount": 11000.0},
            "resolution_note": "Filled tax from manual review.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "edited"
    assert data["next_workflow_status"] == "ready_to_post"

    extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc_id)
        .first()
    )
    assert extraction is not None
    assert float(extraction.tax_amount) == 11000.0
    assert extraction.status == "extracted"

    journal = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.document_id == doc_id)
        .first()
    )
    assert journal is not None
    assert len(journal.lines) == 2

    db_session.refresh(doc)
    assert doc.status == "ready_to_post"
    called_state = mock_bookkeeping_node.call_args.args[0]
    assert called_state["tax_amount"] == 11000.0


def test_reject_review_item_success(client, db_session):
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="inv_003.pdf",
        stored_file_path="/tmp/inv_003.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        status="uploaded",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        document_id=doc_id,
        entry_date=date(2026, 8, 1),
        description="Test Entry",
        status="review_required",
    )
    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="pending",
        priority="high",
        source_type="document",
        source_id=doc_id,
        title="Review Journal Entry",
    )
    db_session.add_all([doc, je, item])
    db_session.commit()

    response = client.post(
        f"/api/v1/review-items/{item_id}/reject",
        json={"resolution_note": "Not a valid business expense"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"

    db_session.refresh(doc)
    db_session.refresh(je)
    assert doc.status == "rejected"
    assert je.status == "rejected"


def test_action_already_resolved_review_item(client, db_session):
    item_id = uuid.uuid4()
    item = ReviewItem(
        id=item_id,
        review_type="bookkeeping",
        status="approved",
        priority="normal",
        source_type="document",
        source_id=uuid.uuid4(),
        title="Already Approved",
    )
    db_session.add(item)
    db_session.commit()

    response = client.post(f"/api/v1/review-items/{item_id}/approve")
    assert response.status_code == 400
    assert "already approved" in response.json()["detail"]
