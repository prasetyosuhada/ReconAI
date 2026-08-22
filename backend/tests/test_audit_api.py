import uuid
from datetime import date, datetime

from app.models.audit import AuditEvent
from app.models.document import Document
from app.models.journal import JournalEntry


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


def test_get_document_audit_log_includes_snapshot_document_id(client, db_session):
    """Verify audit-log endpoint includes review_item and reconciliation events via snapshot document_id."""
    doc_id = uuid.uuid4()
    doc_str = str(doc_id)
    doc = Document(
        id=doc_id,
        original_filename="invoice_05_starbucks_meeting.pdf",
        stored_file_path="/storage/uploads/invoice_05_starbucks_meeting.pdf",
        mime_type="application/pdf",
        file_size_bytes=2048,
        status="posted",
    )

    je_id = uuid.uuid4()
    je = JournalEntry(
        id=je_id,
        document_id=doc_id,
        entry_date=date.today(),
        description="Starbucks meeting expense",
        status="posted",
    )

    # 1. Document event (source_id == doc_id)
    evt_upload = AuditEvent(
        id=uuid.uuid4(),
        event_type="document_uploaded",
        source_type="document",
        source_id=doc_id,
        actor_type="human",
        actor_name="Accountant",
    )
    # 2. Journal Entry event (source_id == je_id)
    evt_je_posted = AuditEvent(
        id=uuid.uuid4(),
        event_type="journal_entry_posted",
        source_type="journal_entry",
        source_id=je_id,
        actor_type="human",
        actor_name="Accountant",
    )
    # 3. Review item event (source_id == review_item_id, document_id in input_snapshot)
    review_item_id = uuid.uuid4()
    evt_review = AuditEvent(
        id=uuid.uuid4(),
        event_type="review_item_approved",
        source_type="review_item",
        source_id=review_item_id,
        actor_type="human",
        actor_name="Reviewer",
        human_action="approved",
        input_snapshot={"document_id": doc_str, "review_item_id": str(review_item_id)},
    )
    # 4. Reconciliation match event (source_id == match_id, document_id in output_snapshot)
    match_id = uuid.uuid4()
    evt_recon = AuditEvent(
        id=uuid.uuid4(),
        event_type="reconciliation_match_accepted",
        source_type="reconciliation_match",
        source_id=match_id,
        actor_type="human",
        actor_name="Auditor",
        human_action="accepted",
        output_snapshot={"document_id": doc_str, "match_id": str(match_id)},
    )
    # 5. Unrelated document event (different document_id)
    unrelated_doc_id = uuid.uuid4()
    evt_unrelated = AuditEvent(
        id=uuid.uuid4(),
        event_type="review_item_approved",
        source_type="review_item",
        source_id=uuid.uuid4(),
        actor_type="human",
        actor_name="Other",
        input_snapshot={"document_id": str(unrelated_doc_id)},
    )

    db_session.add_all([doc, je, evt_upload, evt_je_posted, evt_review, evt_recon, evt_unrelated])
    db_session.commit()

    response = client.get(f"/api/v1/audit-log/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_str

    event_types = [e["event_type"] for e in data["timeline"]]
    assert len(event_types) == 4
    assert "document_uploaded" in event_types
    assert "journal_entry_posted" in event_types
    assert "review_item_approved" in event_types
    assert "reconciliation_match_accepted" in event_types


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


def test_list_audit_events_with_search_and_date_filters(client, db_session):
    now = datetime.now()
    audit = AuditEvent(
        id=uuid.uuid4(),
        event_type="extraction_completed",
        source_type="document",
        source_id=uuid.uuid4(),
        actor_type="agent",
        actor_name="IntakeAgentSpecial",
        rationale="Extracted invoice with high precision",
        created_at=now,
    )
    db_session.add(audit)
    db_session.commit()

    # Search by actor_name
    res = client.get("/api/v1/audit-events?search=IntakeAgentSpecial")
    assert res.status_code == 200
    assert any(i["actor_name"] == "IntakeAgentSpecial" for i in res.json()["items"])

    # Search by rationale
    res_rat = client.get("/api/v1/audit-events?search=high precision")
    assert res_rat.status_code == 200
    assert any("high precision" in (i["rationale"] or "") for i in res_rat.json()["items"])

    # Filter by date
    today_str = now.strftime("%Y-%m-%d")
    res_date = client.get(f"/api/v1/audit-events?start_date={today_str}")
    assert res_date.status_code == 200
    assert len(res_date.json()["items"]) >= 1


def test_cross_entity_audit_trace_endpoints(client, db_session):
    je_id = uuid.uuid4()
    audit_je = AuditEvent(
        id=uuid.uuid4(),
        event_type="journal_entry_suggested",
        source_type="journal_entry",
        source_id=je_id,
        actor_type="agent",
        actor_name="BookkeepingAgent",
        output_snapshot={"journal_entry_id": str(je_id)},
    )
    db_session.add(audit_je)

    # Add a standalone JE without document
    je = JournalEntry(
        id=je_id,
        entry_date=date(2026, 8, 22),
        description="Manual Adjusting Entry",
        status="posted",
        source_type="manual",
    )
    db_session.add(je)
    db_session.commit()

    res = client.get(f"/api/v1/audit-log/journal-entry/{je_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["resolved_entity_type"] == "journal_entry"
    assert len(data["timeline"]) >= 1

