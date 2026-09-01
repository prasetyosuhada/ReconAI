import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.agents.schemas import BookkeepingOutcome
from app.api.v1.review_items import _continue_document_to_bookkeeping
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
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

    # Filter priority=high
    response_prio = client.get("/api/v1/review-items?priority=high")
    assert response_prio.status_code == 200
    data_prio = response_prio.json()
    assert data_prio["total"] == 1
    assert data_prio["items"][0]["title"] == "Review Item Pending"

    # Filter search term
    response_search = client.get("/api/v1/review-items?search=Approved")
    assert response_search.status_code == 200
    data_search = response_search.json()
    assert data_search["total"] == 1
    assert data_search["items"][0]["title"] == "Review Item Approved"


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

    # Verify JournalEntry is posted and document is posted
    db_session.refresh(je)
    db_session.refresh(doc)
    assert je.status == "posted"
    assert doc.status == "posted"

    # Verify AuditEvents created
    audit = db_session.query(AuditEvent).filter(AuditEvent.source_id == item_id).first()
    assert audit is not None
    assert audit.event_type == "review_item_approved"

    posted_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.source_id == je.id,
            AuditEvent.event_type == "journal_entry_posted",
        )
        .first()
    )
    assert posted_audit is not None
    assert posted_audit.output_snapshot["status"] == "posted"
    assert posted_audit.output_snapshot["document_id"] == str(doc_id)


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
    db_session.refresh(doc)
    assert je.status == "posted"
    assert doc.status == "posted"
    assert len(je.lines) == 2

    # Verify journal_entry_posted audit event created
    posted_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.source_id == je.id,
            AuditEvent.event_type == "journal_entry_posted",
        )
        .first()
    )
    assert posted_audit is not None
    assert posted_audit.output_snapshot["status"] == "posted"
    assert posted_audit.output_snapshot["document_id"] == str(doc_id)


@patch(
    "app.api.v1.review_items.perf_counter",
    side_effect=[500.0, 500.42],
)
@patch("app.api.v1.review_items.classify_bookkeeping")
def test_edit_extraction_review_continues_to_bookkeeping(
    mock_classify_bookkeeping, mock_perf_counter, client, db_session
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
    db_session.add_all(
        [
            ChartOfAccount(
                account_code="5100",
                account_name="Supplies Expense",
                account_type="expense",
                normal_balance="debit",
                is_active=True,
            ),
            ChartOfAccount(
                account_code="2000",
                account_name="Accounts Payable",
                account_type="liability",
                normal_balance="credit",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    mock_classify_bookkeeping.return_value = BookkeepingOutcome(
        entry_date="2026-08-01",
        entry_description="Purchase from PT Blur",
        journal_lines=[
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
        total_debit=111000.0,
        total_credit=111000.0,
        is_balanced=True,
        risk_flags=[],
        confidence_score=0.91,
        rationale="Human-reviewed extraction is bookkept.",
        status="ready_to_post",
        needs_review=False,
    )

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
    called_extraction = mock_classify_bookkeeping.call_args.kwargs["extraction_data"]
    assert called_extraction["tax_amount"] == 11000.0
    continuation_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "bookkeeping_completed",
            AuditEvent.source_id == journal.id,
        )
        .one()
    )
    assert continuation_audit.source_type == "journal_entry"
    assert continuation_audit.input_snapshot["triggered_by"] == (
        "extraction_review_approval"
    )
    assert continuation_audit.output_snapshot["processing_duration_ms"] == 420.0
    assert continuation_audit.created_at > item.resolved_at
    assert mock_perf_counter.call_count == 2


@patch("app.api.v1.review_items.classify_bookkeeping")
def test_extraction_review_continuation_retry_is_idempotent(
    mock_classify_bookkeeping, db_session
):
    doc = Document(
        id=uuid.uuid4(),
        original_filename="retry_invoice.pdf",
        stored_file_path="/tmp/retry_invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        document_type="invoice",
        status="extraction_review_required",
    )
    extraction_review = ReviewItem(
        id=uuid.uuid4(),
        review_type="extraction",
        status="pending",
        priority="normal",
        source_type="document",
        source_id=doc.id,
        title="Review retry extraction",
    )
    db_session.add_all(
        [
            doc,
            extraction_review,
            ChartOfAccount(
                account_code="5100",
                account_name="Supplies Expense",
                account_type="expense",
                normal_balance="debit",
                is_active=True,
            ),
            ChartOfAccount(
                account_code="2000",
                account_name="Accounts Payable",
                account_type="liability",
                normal_balance="credit",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    mock_classify_bookkeeping.return_value = BookkeepingOutcome(
        entry_date="2026-08-01",
        entry_description="Retry-safe purchase",
        journal_lines=[
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
        total_debit=111000.0,
        total_credit=111000.0,
        is_balanced=True,
        risk_flags=["low_confidence_classification"],
        confidence_score=0.75,
        rationale="Needs a bookkeeping review.",
        status="bookkeeping_review_required",
        needs_review=True,
    )
    payload = {
        "document_type": "invoice",
        "vendor_name": "PT Retry",
        "transaction_date": "2026-08-01",
        "subtotal_amount": 100000.0,
        "tax_amount": 11000.0,
        "total_amount": 111000.0,
        "currency": "IDR",
        "line_items": [],
    }

    for _ in range(2):
        next_status = _continue_document_to_bookkeeping(
            item=extraction_review,
            payload=payload,
            resolution_note="Approved extraction retry.",
            db=db_session,
        )
        assert next_status == "bookkeeping_review_required"
        db_session.commit()

    journals = (
        db_session.query(JournalEntry).filter(JournalEntry.document_id == doc.id).all()
    )
    bookkeeping_reviews = (
        db_session.query(ReviewItem)
        .filter(
            ReviewItem.review_type == "bookkeeping",
            ReviewItem.status == "pending",
        )
        .all()
    )
    assert len(journals) == 1
    assert len(bookkeeping_reviews) == 1
    assert bookkeeping_reviews[0].source_id == journals[0].id
    bookkeeping_audits = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "bookkeeping_completed",
            AuditEvent.source_id == journals[0].id,
        )
        .all()
    )
    assert len(bookkeeping_audits) == 1


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


def test_review_queue_header_counts_independent_of_pagination(client, db_session):
    """Confirm summary badge queries (pending, high priority, resolved_today) are unpaginated & invariant across pages."""
    # Create 15 pending items (5 high priority, 10 normal)
    for i in range(15):
        db_session.add(
            ReviewItem(
                id=uuid.uuid4(),
                review_type="bookkeeping",
                status="pending",
                priority="high" if i < 5 else "normal",
                source_type="document",
                source_id=uuid.uuid4(),
                title=f"Pending Item {i}",
                summary="Needs review",
            )
        )
    # Create 4 posted items: 3 resolved today, 1 resolved 5 days ago
    now = datetime.now(UTC)
    for i in range(4):
        db_session.add(
            ReviewItem(
                id=uuid.uuid4(),
                review_type="extraction",
                status="posted",
                priority="normal",
                source_type="document",
                source_id=uuid.uuid4(),
                title=f"Posted Item {i}",
                summary="Already posted",
                resolved_at=now if i < 3 else (now - timedelta(days=5)),
            )
        )
    db_session.commit()

    # --- Page 1 (offset=0, limit=10) ---
    p1_items_res = client.get(
        "/api/v1/review-items?status=pending&limit=10&offset=0"
    ).json()
    assert len(p1_items_res["items"]) == 10
    assert p1_items_res["total"] == 15

    # Header queries on Page 1
    p1_pending = client.get("/api/v1/review-items?status=pending&limit=1").json()[
        "total"
    ]
    p1_high = client.get(
        "/api/v1/review-items?status=pending&priority=high&limit=1"
    ).json()["total"]
    p1_resolved_today = client.get(
        "/api/v1/review-items?resolved_today=true&limit=1"
    ).json()["total"]

    assert p1_pending == 15
    assert p1_high == 5
    assert (
        p1_resolved_today == 3
    )  # exactly the 3 resolved today, not the 4th from 5 days ago

    # --- Page 2 (offset=10, limit=10) ---
    p2_items_res = client.get(
        "/api/v1/review-items?status=pending&limit=10&offset=10"
    ).json()
    assert len(p2_items_res["items"]) == 5
    assert p2_items_res["total"] == 15

    # Header queries on Page 2
    p2_pending = client.get("/api/v1/review-items?status=pending&limit=1").json()[
        "total"
    ]
    p2_high = client.get(
        "/api/v1/review-items?status=pending&priority=high&limit=1"
    ).json()["total"]
    p2_resolved_today = client.get(
        "/api/v1/review-items?resolved_today=true&limit=1"
    ).json()["total"]

    assert p2_pending == 15
    assert p2_high == 5
    assert p2_resolved_today == 3

    # Assert 100% invariance between Page 1 and Page 2 header metrics
    assert p1_pending == p2_pending
    assert p1_high == p2_high
    assert p1_resolved_today == p2_resolved_today
