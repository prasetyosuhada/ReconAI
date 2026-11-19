import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem


def test_list_journal_entries_empty(client):
    response = client.get("/api/v1/ledger")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_get_journal_entry_detail(client, db_session):
    je_id = uuid.uuid4()
    coa_id = uuid.uuid4()

    coa = ChartOfAccount(
        id=coa_id,
        account_code="5100",
        account_name="Office Supplies Expense",
        account_type="expense",
        normal_balance="debit",
    )
    je = JournalEntry(
        id=je_id,
        entry_date=date(2026, 8, 1),
        description="Office Supplies",
        status="posted",
    )
    line = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=je_id,
        account_id=coa_id,
        line_number=1,
        debit_amount=150000.0,
        credit_amount=0.0,
        description="Supplies purchase",
    )
    db_session.add_all([coa, je, line])
    db_session.commit()

    response = client.get(f"/api/v1/ledger/journal-entries/{je_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(je_id)
    assert data["description"] == "Office Supplies"
    assert len(data["lines"]) == 1
    assert data["lines"][0]["account_code"] == "5100"
    assert data["lines"][0]["debit_amount"] == 150000.0


@pytest.fixture
def ready_entry(db_session):
    document = Document(
        original_filename="invoice.pdf",
        stored_file_path="invoice.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        status="ready_to_post",
    )
    entry = JournalEntry(
        document=document,
        entry_date=date(2026, 8, 1),
        description="Office supplies",
        status="draft",
    )
    for index, (code, debit, credit) in enumerate(
        [("5100", 100, 0), ("2000", 0, 100)], start=1
    ):
        account = ChartOfAccount(
            account_code=code,
            account_name=code,
            account_type="expense" if debit else "liability",
            normal_balance="debit" if debit else "credit",
        )
        entry.lines.append(
            JournalEntryLine(
                account=account,
                line_number=index,
                debit_amount=debit,
                credit_amount=credit,
            )
        )
    db_session.add(entry)
    db_session.commit()
    return entry


def add_review(
    db_session, entry, *, status="pending", source="journal_entry", **kwargs
):
    review = ReviewItem(
        review_type="bookkeeping",
        title="Review journal",
        source_type=source,
        source_id=entry.id if source == "journal_entry" else entry.document_id,
        status=status,
        **kwargs,
    )
    db_session.add(review)
    db_session.commit()
    return review


def test_direct_post_commits_once_with_audit(client, db_session, ready_entry):
    journal_id, document_id = ready_entry.id, ready_entry.document_id
    path = f"/api/v1/ledger/journal-entries/{journal_id}/post"
    commits = []

    def count_commit(session):
        commits.append(session)

    event.listen(Session, "after_commit", count_commit)
    try:
        response = client.post(path)
    finally:
        event.remove(Session, "after_commit", count_commit)
    assert len(commits) == 1
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(journal_id)
    assert data["status"] == "posted"
    assert data["trial_balance_status"] == "balanced"

    repeat = client.post(path)
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "journal_already_posted"
    db_session.refresh(ready_entry)
    assert ready_entry.status == ready_entry.document.status == "posted"
    assert ready_entry.posted_at.replace(tzinfo=UTC) == datetime.fromisoformat(
        data["posted_at"]
    )
    audit = db_session.query(AuditEvent).one()
    assert audit.event_type == "journal_entry_posted"
    assert audit.source_id == journal_id
    assert audit.actor_name == "api_user"
    assert audit.output_snapshot == {
        "journal_entry_id": str(journal_id),
        "document_id": str(document_id),
        "gl_period": "2026-08",
        "status": "posted",
    }


@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_direct_post_rolls_back_flushed_writes(
    client, db_session, ready_entry, monkeypatch, failure
):
    def fail(session):
        session.flush()
        raise RuntimeError("private persistence detail")

    if failure == "audit":

        def fail_audit(db, **kwargs):
            fail(db)

        monkeypatch.setattr("app.services.journal_posting.log_event", fail_audit)
    else:
        monkeypatch.setattr(Session, "commit", fail)
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "posting_failed"
    assert "private persistence detail" not in response.text
    db_session.refresh(ready_entry)
    assert ready_entry.status == "draft"
    assert ready_entry.posted_at is None
    assert ready_entry.document.status == "ready_to_post"
    assert db_session.query(AuditEvent).count() == 0


@pytest.mark.parametrize(
    ("journal_status", "doc_status", "source", "expected"),
    [
        ("approved", "approved", "document", 200),
        ("approved", None, "document", 200),
        ("draft", None, "manual", 200),
        ("draft", None, "document", 409),
        ("draft", "approved", "document", 409),
        ("approved", "failed", "document", 409),
        ("voided", "ready_to_post", "document", 409),
        ("rejected", "ready_to_post", "document", 409),
        ("unknown", "ready_to_post", "document", 409),
    ],
)
def test_direct_post_workflow_states(
    client, db_session, ready_entry, journal_status, doc_status, source, expected
):
    ready_entry.status = journal_status
    ready_entry.source_type = source
    if doc_status is None:
        ready_entry.document = None
    else:
        ready_entry.document.status = doc_status
    db_session.commit()
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == expected
    if expected == 409:
        assert response.json()["error"]["code"] == "journal_not_postable"
        assert db_session.query(AuditEvent).count() == 0


@pytest.mark.parametrize(
    "gate",
    [
        "sensitive_code",
        "sensitive_coa",
        "risk",
        "low_confidence",
        "journal_status",
        "extraction",
        "pending",
        "cancelled",
        "rejected",
    ],
)
def test_direct_post_cannot_bypass_review(client, db_session, ready_entry, gate):
    ready_entry.status = "approved"
    if gate == "sensitive_code":
        ready_entry.lines[0].account.account_code = "1010"
    elif gate == "sensitive_coa":
        ready_entry.lines[0].account.is_sensitive = True
    elif gate == "risk":
        ready_entry.risk_flags = ["requires_review"]
    elif gate == "low_confidence":
        ready_entry.confidence_score = 0.80
    elif gate == "journal_status":
        ready_entry.status = "review_required"
    elif gate == "extraction":
        db_session.add(
            ReviewItem(
                review_type="extraction",
                source_type="document",
                source_id=ready_entry.document_id,
                title="Review extraction",
                status="pending",
            )
        )
    else:
        add_review(db_session, ready_entry, status=gate)
    db_session.commit()
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "posting_review_required"
    assert db_session.query(AuditEvent).count() == 0
    assert ready_entry.document.status == "ready_to_post"


@pytest.mark.parametrize(
    ("status", "source", "amount", "expected"),
    [
        ("approved", "journal_entry", 100, 200),
        ("edited", "document", 100, 200),
        ("approved", "document", 100, 200),
        ("approved", "document", 90, 409),
        ("edited", "journal_entry", 90, 409),
    ],
)
def test_direct_post_checks_reviewed_lines(
    client, db_session, ready_entry, status, source, amount, expected
):
    ready_entry.risk_flags = ["requires_review"]
    lines_key = (
        "journal_lines" if source == "document" and status == "approved" else "lines"
    )
    payload = {
        lines_key: [
            {"account_code": "5100", "debit_amount": amount},
            {"account_code": "2000", "credit_amount": amount},
        ]
    }
    add_review(
        db_session,
        ready_entry,
        status=status,
        source=source,
        original_payload=payload
        if status == "approved"
        else {"journal_entry_id": str(ready_entry.id)},
        edited_payload=payload if status == "edited" else None,
    )
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == expected
    if expected == 409:
        assert response.json()["error"]["code"] == "posting_review_required"


@pytest.mark.parametrize(
    ("target", "expected"),
    [("none", 409), ("missing", 409), ("sibling", 200), ("self", 409)],
)
def test_direct_post_verifies_document_review_target(
    client, db_session, ready_entry, target, expected
):
    sibling = JournalEntry(
        document_id=ready_entry.document_id,
        entry_date=date.today(),
        description="Other",
    )
    db_session.add(sibling)
    db_session.flush()
    ids = {"missing": uuid.uuid4(), "sibling": sibling.id, "self": ready_entry.id}
    payload = {"journal_entry_id": str(ids[target])} if target in ids else {}
    add_review(db_session, ready_entry, source="document", original_payload=payload)
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == expected
    if expected == 409:
        code = "posting_review_required" if target == "self" else "journal_not_postable"
        assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("invalid", ["unbalanced", "inactive"])
def test_direct_post_checks_effective_journal(client, db_session, ready_entry, invalid):
    if invalid == "unbalanced":
        ready_entry.lines[0].debit_amount = 99
    else:
        ready_entry.lines[0].account.is_active = False
    db_session.commit()
    response = client.post(f"/api/v1/ledger/journal-entries/{ready_entry.id}/post")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "journal_validation_failed"
    db_session.refresh(ready_entry)
    assert ready_entry.status == "draft"
    assert ready_entry.document.status == "ready_to_post"
    assert ready_entry.posted_at is None
    assert db_session.query(AuditEvent).count() == 0


@pytest.mark.parametrize(
    ("journal_id", "status", "code"),
    [
        ("invalid", 400, "invalid_id"),
        (str(uuid.uuid4()), 404, "not_found"),
    ],
)
def test_direct_post_target_errors(client, journal_id, status, code):
    response = client.post(f"/api/v1/ledger/journal-entries/{journal_id}/post")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_list_chart_of_accounts(client, db_session):
    coa1 = ChartOfAccount(
        id=uuid.uuid4(),
        account_code="1000",
        account_name="Cash",
        account_type="asset",
        normal_balance="debit",
        is_sensitive=True,
    )
    coa2 = ChartOfAccount(
        id=uuid.uuid4(),
        account_code="4000",
        account_name="Revenue",
        account_type="revenue",
        normal_balance="credit",
        is_sensitive=False,
    )
    db_session.add_all([coa1, coa2])
    db_session.commit()

    response = client.get("/api/v1/ledger/chart-of-accounts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["account_code"] == "1000"


def test_get_trial_balance_balanced(client, db_session):
    je_id = uuid.uuid4()
    coa1_id = uuid.uuid4()
    coa2_id = uuid.uuid4()

    coa1 = ChartOfAccount(
        id=coa1_id,
        account_code="5100",
        account_name="Office Supplies",
        account_type="expense",
        normal_balance="debit",
    )
    coa2 = ChartOfAccount(
        id=coa2_id,
        account_code="1010",
        account_name="Bank Account",
        account_type="asset",
        normal_balance="debit",
    )
    je = JournalEntry(
        id=je_id,
        entry_date=date(2026, 8, 1),
        description="Posted Office Purchase",
        status="posted",
    )
    line1 = JournalEntryLine(
        journal_entry_id=je_id,
        account_id=coa1_id,
        line_number=1,
        debit_amount=250000.0,
        credit_amount=0.0,
    )
    line2 = JournalEntryLine(
        journal_entry_id=je_id,
        account_id=coa2_id,
        line_number=2,
        debit_amount=0.0,
        credit_amount=250000.0,
    )
    db_session.add_all([coa1, coa2, je, line1, line2])
    db_session.commit()

    response = client.get("/api/v1/ledger/trial-balance")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "balanced"
    assert data["total_debits"] == 250000.0
    assert data["total_credits"] == 250000.0
    assert data["difference"] == 0.0
    assert len(data["accounts"]) == 2


def test_list_journal_entries_with_search(client, db_session):
    je1 = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 10),
        description="AWS Cloud Server Hosting Payment",
        status="posted",
    )
    je2 = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 12),
        description="Office Coffee Machine Restock",
        status="draft",
    )
    db_session.add_all([je1, je2])
    db_session.commit()

    # Search description
    res_desc = client.get("/api/v1/ledger/journal-entries?search=Server+Hosting")
    assert res_desc.status_code == 200
    assert len(res_desc.json()["items"]) == 1
    assert (
        res_desc.json()["items"][0]["description"] == "AWS Cloud Server Hosting Payment"
    )

    # Search date
    res_date = client.get("/api/v1/ledger/journal-entries?search=2026-08-12")
    assert res_date.status_code == 200
    assert any(
        i["description"] == "Office Coffee Machine Restock"
        for i in res_date.json()["items"]
    )
