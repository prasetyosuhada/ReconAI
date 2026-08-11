import io
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

    # Verify background task enqueued
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
