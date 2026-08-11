import io
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry
from app.models.review import ReviewItem
from app.services.document_processing import process_document_background


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


@patch("app.api.v1.documents.process_document_background")
def test_upload_document_success_pdf(mock_bg_task):
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


def test_upload_document_unsupported_type():
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


def test_upload_document_empty_file():
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
def test_process_document_background_success(mock_session_class, mock_graph):
    # Setup database session override for service test
    db = TestingSessionLocal()
    mock_session_class.return_value = db

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
    db.add(doc)
    db.commit()

    mock_graph.invoke.return_value = {
        "document_id": str(doc_id),
        "vendor_name": "Toko Gramedia",
        "transaction_date": "2026-08-01",
        "subtotal_amount": 100000.0,
        "tax_amount": 11000.0,
        "total_amount": 111000.0,
        "currency": "IDR",
        "confidence_score": 0.95,
        "rationale": "High confidence extraction",
        "status": "extracted",
        "needs_review": False,
        "journal_entry": [
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
    }

    process_document_background(
        document_id=str(doc_id),
        stored_file_path="/tmp/invoice_office.pdf",
        mime_type="application/pdf",
        original_filename="invoice_office.pdf",
        document_type="invoice",
    )

    # Verify Extraction record created
    ext = (
        db.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc_id)
        .first()
    )
    assert ext is not None
    assert ext.vendor_name == "Toko Gramedia"

    # Verify Journal Entry created
    je = db.query(JournalEntry).filter(JournalEntry.document_id == doc_id).first()
    assert je is not None
    assert len(je.lines) == 2

    # Verify Audit Event recorded
    audit = db.query(AuditEvent).filter(AuditEvent.source_id == doc_id).first()
    assert audit is not None
    assert audit.event_type == "extraction_completed"


@patch("app.services.document_processing.document_processing_graph")
@patch("app.services.document_processing.SessionLocal")
def test_process_document_background_review_required(mock_session_class, mock_graph):
    db = TestingSessionLocal()
    mock_session_class.return_value = db

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
    db.add(doc)
    db.commit()

    mock_graph.invoke.return_value = {
        "document_id": str(doc_id),
        "vendor_name": "Unknown Vendor",
        "confidence_score": 0.60,
        "status": "extraction_review_required",
        "needs_review": True,
        "risk_flags": ["low_confidence_extraction"],
    }

    process_document_background(
        document_id=str(doc_id),
        stored_file_path="/tmp/low_confidence.pdf",
        mime_type="application/pdf",
        original_filename="low_confidence.pdf",
    )

    # Verify ReviewItem created
    review = db.query(ReviewItem).filter(ReviewItem.source_id == doc_id).first()
    assert review is not None
    assert review.status == "pending"
    assert review.review_type == "extraction"
