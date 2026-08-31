import io
import json
import uuid
from unittest.mock import patch

from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.document_processing import process_document_background


@patch("app.api.v1.documents.process_document_background")
def test_upload_document_success_pdf(mock_bg_task, client):
    file_content = b"%PDF-1.4 dummy pdf content for invoice"
    file = ("receipt_001.pdf", io.BytesIO(file_content), "application/pdf")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": file},
        data={"document_type": "receipt"},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["original_filename"] == "receipt_001.pdf"
    assert data["document_type"] == "receipt"
    assert data["status"] == "extracting"
    assert "links" in data
    assert data["links"]["self"].endswith(data["id"])

    mock_bg_task.assert_called_once()


def test_upload_document_unsupported_type(client):
    file_content = b"Plain text file content"
    file = ("notes.txt", io.BytesIO(file_content), "text/plain")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": file},
        data={"document_type": "unknown"},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Unsupported file type" in data["detail"]


def test_upload_document_empty_file(client):
    file_content = b""
    file = ("empty.pdf", io.BytesIO(file_content), "application/pdf")

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": file},
    )

    assert response.status_code == 400
    data = response.json()
    assert "Uploaded file is empty" in data["detail"]


@patch("app.services.document_processing.document_processing_graph")
@patch("app.services.document_processing.SessionLocal")
def test_process_document_background_separates_agent_metadata(
    mock_session_class, mock_graph, db_session
):
    mock_session_class.return_value = db_session
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
                account_name="Accounts Payable",
                account_type="liability",
                normal_balance="credit",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="invoice_office.pdf",
        stored_file_path="/tmp/invoice_office.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        document_type="invoice",
        status="uploaded",
    )
    db_session.add(doc)
    db_session.commit()

    intake_res = {
        "document_id": str(doc_id),
        "vendor_name": "Toko Gramedia",
        "transaction_date": "2026-08-01",
        "subtotal_amount": 100000.0,
        "tax_amount": 11000.0,
        "total_amount": 111000.0,
        "currency": "IDR",
        "confidence_score": 0.96,
        "rationale": "High confidence extraction",
        "status": "extracted",
        "needs_review": False,
    }
    bookkeeping_res = {
        "journal_lines": [
            {
                "account_code": "5100",
                "account_name": "Supplies",
                "debit_amount": 111000.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "2000",
                "account_name": "AP",
                "debit_amount": 0.0,
                "credit_amount": 111000.0,
            },
        ],
        "is_balanced": True,
        "uses_sensitive_account": False,
        "risk_flags": ["low_confidence_classification"],
        "confidence_score": 0.80,
        "rationale": "Account classification requires review",
        "status": "bookkeeping_review_required",
        "needs_review": True,
    }

    mock_graph.stream.return_value = [
        {"document_intake": intake_res},
        {"bookkeeping": bookkeeping_res},
    ]

    process_document_background(
        document_id=str(doc_id),
        stored_file_path="/tmp/invoice_office.pdf",
        mime_type="application/pdf",
        original_filename="invoice_office.pdf",
        document_type="invoice",
    )

    # Verify Extraction record created
    ext = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc_id)
        .first()
    )
    assert ext is not None
    assert ext.vendor_name == "Toko Gramedia"
    assert float(ext.confidence_score) == 0.96
    assert ext.rationale == "High confidence extraction"
    assert ext.status == "extracted"

    # Verify Journal Entry created
    je = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.document_id == doc_id)
        .first()
    )
    assert je is not None
    assert len(je.lines) == 2
    assert float(je.confidence_score) == 0.80
    assert je.rationale == "Account classification requires review"

    # Verify each audit event retains the metadata of its owning agent.
    extraction_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "extraction_completed",
            AuditEvent.source_id == doc_id,
        )
        .one()
    )
    assert float(extraction_audit.confidence_score) == 0.96
    assert extraction_audit.rationale == "High confidence extraction"
    assert extraction_audit.output_snapshot["status"] == "extracted"
    assert extraction_audit.output_snapshot["needs_review"] is False

    bookkeeping_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "bookkeeping_completed",
            AuditEvent.source_id == je.id,
        )
        .one()
    )
    assert float(bookkeeping_audit.confidence_score) == 0.80
    assert bookkeeping_audit.rationale == "Account classification requires review"

    persisted_doc = db_session.query(Document).filter(Document.id == doc_id).one()
    assert persisted_doc.status == "bookkeeping_review_required"


@patch("app.services.document_processing.document_processing_graph")
@patch("app.services.document_processing.SessionLocal")
def test_process_document_background_review_required(
    mock_session_class, mock_graph, db_session
):
    mock_session_class.return_value = db_session

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="low_confidence.pdf",
        stored_file_path="/tmp/low_confidence.pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        document_type="invoice",
        status="uploaded",
    )
    db_session.add(doc)
    db_session.commit()

    intake_res = {
        "document_id": str(doc_id),
        "vendor_name": "Unknown Vendor",
        "confidence_score": 0.60,
        "rationale": "Extraction is uncertain",
        "status": "extraction_review_required",
        "needs_review": True,
        "risk_flags": ["low_confidence_extraction"],
    }

    mock_graph.stream.return_value = [
        {"document_intake": intake_res},
        {"review_router": {"needs_review": True}},
    ]

    process_document_background(
        document_id=str(doc_id),
        stored_file_path="/tmp/low_confidence.pdf",
        mime_type="application/pdf",
        original_filename="low_confidence.pdf",
    )

    # Verify ReviewItem created
    review = db_session.query(ReviewItem).filter(ReviewItem.source_id == doc_id).first()
    assert review is not None
    assert review.status == "pending"
    assert review.review_type == "extraction"

    extraction = (
        db_session.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc_id)
        .one()
    )
    assert float(extraction.confidence_score) == 0.60
    assert extraction.rationale == "Extraction is uncertain"
    assert extraction.status == "draft"

    extraction_audit = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "extraction_completed",
            AuditEvent.source_id == doc_id,
        )
        .one()
    )
    assert float(extraction_audit.confidence_score) == 0.60
    assert extraction_audit.output_snapshot["status"] == "extraction_review_required"
    assert extraction_audit.output_snapshot["needs_review"] is True
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == "bookkeeping_completed")
        .count()
        == 0
    )


@patch("app.services.document_processing.document_processing_graph")
@patch("app.services.document_processing.SessionLocal")
def test_stream_document_processing_sse(
    mock_session_class, mock_graph, client, db_session
):
    mock_session_class.return_value = db_session

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="stream_invoice.pdf",
        stored_file_path="/tmp/stream_invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        document_type="invoice",
        status="uploaded",
    )
    db_session.add(doc)
    db_session.commit()

    intake_res = {
        "document_id": str(doc_id),
        "vendor_name": "PLN Indonesia",
        "transaction_date": "2026-08-01",
        "subtotal_amount": 500000.0,
        "tax_amount": 55000.0,
        "total_amount": 555000.0,
        "currency": "IDR",
        "confidence_score": 0.95,
        "status": "extracted",
        "needs_review": False,
    }
    bookkeeping_res = {
        "journal_lines": [
            {
                "account_code": "5200",
                "account_name": "Electricity",
                "debit_amount": 555000.0,
                "credit_amount": 0.0,
            },
            {
                "account_code": "1010",
                "account_name": "Bank Account",
                "debit_amount": 0.0,
                "credit_amount": 555000.0,
            },
        ],
        "is_balanced": True,
        "uses_sensitive_account": True,
        "confidence_score": 0.80,
        "rationale": "Sensitive payment account requires review",
        "status": "bookkeeping_review_required",
        "needs_review": True,
    }

    mock_graph.stream.return_value = [
        {"document_intake": intake_res},
        {"bookkeeping": bookkeeping_res},
    ]

    response = client.get(f"/api/v1/documents/stream/{doc_id}")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "data:" in response.text
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    intake_done = next(event for event in events if event["stage"] == "intake_done")
    completed = next(event for event in events if event["stage"] == "completed")
    assert intake_done["confidence_score"] == 0.95
    assert completed["confidence_score"] == 0.80


def test_list_documents_status_filtering(client, db_session):
    """Test filtering documents by umbrella and exact status values."""
    docs = [
        Document(
            id=uuid.uuid4(),
            original_filename="doc_ext_rev.pdf",
            stored_file_path="/tmp/doc1.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            document_type="invoice",
            status="extraction_review_required",
        ),
        Document(
            id=uuid.uuid4(),
            original_filename="doc_bk_rev.pdf",
            stored_file_path="/tmp/doc2.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            document_type="invoice",
            status="bookkeeping_review_required",
        ),
        Document(
            id=uuid.uuid4(),
            original_filename="doc_ready.pdf",
            stored_file_path="/tmp/doc3.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            document_type="receipt",
            status="ready_to_post",
        ),
        Document(
            id=uuid.uuid4(),
            original_filename="doc_proc.pdf",
            stored_file_path="/tmp/doc4.pdf",
            mime_type="application/pdf",
            file_size_bytes=1024,
            document_type="invoice",
            status="extracting",
        ),
    ]
    for d in docs:
        db_session.add(d)
    db_session.commit()

    # 1. Umbrella review_required filter (should match extraction_review_required and bookkeeping_review_required)
    res = client.get("/api/v1/documents?status=review_required")
    assert res.status_code == 200
    items = res.json()["items"]
    statuses = {item["status"] for item in items}
    assert "extraction_review_required" in statuses
    assert "bookkeeping_review_required" in statuses
    assert "ready_to_post" not in statuses

    # 2. Specific extraction_review_required filter
    res_ext = client.get("/api/v1/documents?status=extraction_review_required")
    assert res_ext.status_code == 200
    ext_items = res_ext.json()["items"]
    assert all(item["status"] == "extraction_review_required" for item in ext_items)

    # 3. Specific ready_to_post filter
    res_ready = client.get("/api/v1/documents?status=ready_to_post")
    assert res_ready.status_code == 200
    ready_items = res_ready.json()["items"]
    assert all(item["status"] == "ready_to_post" for item in ready_items)
    assert any(item["original_filename"] == "doc_ready.pdf" for item in ready_items)

    # 4. Processing umbrella filter (matching 'extracting')
    res_proc = client.get("/api/v1/documents?status=processing")
    assert res_proc.status_code == 200
    proc_items = res_proc.json()["items"]
    assert any(item["status"] == "extracting" for item in proc_items)
