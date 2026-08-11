import uuid

from app.models.audit import AuditEvent
from app.models.document import Document


def test_get_document_audit_log_not_found(client):
    random_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/audit-log/{random_id}")
    assert response.status_code == 404
    assert f"Document [{random_id}] not found." in response.json()["detail"]


def test_get_document_audit_log_success(client, db_session):
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="invoice_1001.pdf",
        stored_file_path="/storage/uploads/invoice_1001.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        status="processed",
    )

    audit1 = AuditEvent(
        id=uuid.uuid4(),
        event_type="document_uploaded",
        source_type="document",
        source_id=doc_id,
        actor_type="human",
        actor_name="user",
        input_snapshot={"filename": "invoice_1001.pdf"},
    )
    audit2 = AuditEvent(
        id=uuid.uuid4(),
        event_type="extraction_completed",
        source_type="document",
        source_id=doc_id,
        actor_type="agent",
        actor_name="DocumentIntakeAgent",
        confidence_score=0.95,
    )

    db_session.add_all([doc, audit1, audit2])
    db_session.commit()

    response = client.get(f"/api/v1/audit-log/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["filename"] == "invoice_1001.pdf"
    assert len(data["timeline"]) == 2
    assert data["timeline"][0]["event_type"] == "document_uploaded"
    assert data["timeline"][1]["event_type"] == "extraction_completed"


def test_list_audit_events(client, db_session):
    audit1 = AuditEvent(
        id=uuid.uuid4(),
        event_type="review_item_approved",
        source_type="review_item",
        source_id=uuid.uuid4(),
        actor_type="human",
        actor_name="reviewer",
    )
    db_session.add(audit1)
    db_session.commit()

    response = client.get("/api/v1/audit-events?event_type=review_item_approved")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["event_type"] == "review_item_approved"


def test_get_audit_event_detail(client, db_session):
    event_id = uuid.uuid4()
    audit = AuditEvent(
        id=event_id,
        event_type="journal_entry_posted",
        source_type="journal_entry",
        source_id=uuid.uuid4(),
        actor_type="system",
        input_snapshot={"posted_by": "api_user"},
        output_snapshot={"status": "posted"},
    )
    db_session.add(audit)
    db_session.commit()

    response = client.get(f"/api/v1/audit-events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(event_id)
    assert data["event_type"] == "journal_entry_posted"
    assert data["input_snapshot"]["posted_by"] == "api_user"
