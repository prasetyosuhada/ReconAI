from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.services import journal_posting


def lines(amount):
    return [
        {"account_code": "5100", "debit_amount": amount},
        {"account_code": "1010", "credit_amount": amount},
    ]


@pytest.fixture
def pending(db_session):
    doc = Document(
        original_filename="receipt.pdf",
        stored_file_path="receipt.pdf",
        mime_type="application/pdf",
        file_size_bytes=20,
        status="bookkeeping_review_required",
    )
    entry = JournalEntry(
        document=doc,
        entry_date=date(2026, 8, 1),
        description="Receipt",
        status="review_required",
        risk_flags=["uses_sensitive_account"],
    )
    for number, line in enumerate(lines(100), 1):
        account = ChartOfAccount(
            account_code=line["account_code"],
            account_name=line["account_code"],
            account_type="expense" if number == 1 else "asset",
            normal_balance="debit",
        )
        entry.lines.append(
            JournalEntryLine(
                account=account,
                line_number=number,
                debit_amount=line.get("debit_amount", 0),
                credit_amount=line.get("credit_amount", 0),
            )
        )
    db_session.add(entry)
    db_session.flush()
    review = ReviewItem(
        source_type="journal_entry",
        source_id=entry.id,
        review_type="bookkeeping",
        title="Check receipt",
        original_payload={"journal_entry_id": str(entry.id), "lines": lines(100)},
    )
    db_session.add(review)
    db_session.commit()
    return entry, review


def decision_request(client, review, action, edits=None):
    body = {"resolution_note": "Checked receipt"}
    if action == "edit":
        body["edited_payload"] = (
            edits
            if edits is not None
            else {
                "journal_lines": lines(125),
                "description": "Corrected receipt",
                "entry_date": "2026-09-01",
            }
        )
    return client.post(f"/api/v1/review-items/{review.id}/{action}", json=body)


@pytest.mark.parametrize("action", ["approve", "edit"])
def test_review_commits_once_with_ordered_linked_audit(
    client, db_session, pending, action
):
    entry, review = pending
    commits = []

    def count(session):
        commits.append(session)

    event.listen(Session, "after_commit", count)
    try:
        response = decision_request(client, review, action)
    finally:
        event.remove(Session, "after_commit", count)
    assert response.status_code == 200, response.text
    assert len(commits) == 1
    db_session.expire_all()
    decision = "approved" if action == "approve" else "edited"
    assert review.status == response.json()["status"] == decision
    assert (
        response.json()["next_workflow_status"]
        == entry.status
        == entry.document.status
        == "posted"
    )
    assert review.original_payload["lines"] == lines(100)
    assert review.resolution_note == "Checked receipt"
    if action == "edit":
        assert review.edited_payload["journal_lines"] == lines(125)
        assert entry.description == "Corrected receipt"
        assert entry.entry_date == date(2026, 9, 1)
        assert entry.lines[0].debit_amount == entry.lines[1].credit_amount == 125
    human, posting = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert (
        human.created_at == review.resolved_at < entry.posted_at == posting.created_at
    )
    assert human.actor_name == posting.actor_name == review.resolved_by == "human_user"
    assert (human.source_type, human.source_id, human.event_type) == (
        "review_item",
        review.id,
        f"review_item_{decision}",
    )
    assert (posting.source_type, posting.source_id, posting.event_type) == (
        "journal_entry",
        entry.id,
        "journal_entry_posted",
    )
    assert human.output_snapshot["next_workflow_status"] == "posted"
    assert human.output_snapshot["journal_entry_id"] == str(entry.id)
    assert human.input_snapshot["resolution_note"] == review.resolution_note
    assert posting.output_snapshot["review_item_id"] == str(review.id)
    assert posting.output_snapshot["gl_period"] == entry.entry_date.strftime("%Y-%m")
    assert (
        posting.output_snapshot["document_id"]
        == human.output_snapshot["document_id"]
        == str(entry.document_id)
    )


@pytest.mark.parametrize("action", ["approve", "edit"])
@pytest.mark.parametrize("failure", ["second_audit", "commit"])
def test_failure_rolls_back_review_journal_lines_document_and_audits(
    client, db_session, pending, monkeypatch, action, failure
):
    entry, review = pending
    before_ids = [line.id for line in entry.lines]

    def fail(session):
        session.flush()
        raise RuntimeError("private persistence detail")

    if failure == "second_audit":
        log = journal_posting.log_event

        def fail_post_audit(**kwargs):
            if kwargs["event_type"] == "journal_entry_posted":
                fail(kwargs["db"])
            return log(**kwargs)

        monkeypatch.setattr(journal_posting, "log_event", fail_post_audit)
    else:
        monkeypatch.setattr(Session, "commit", fail)
    response = decision_request(client, review, action)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "posting_failed"
    assert "private persistence detail" not in response.text
    db_session.expire_all()
    assert review.status == "pending"
    assert (
        review.resolution_note
        is review.resolved_at
        is review.resolved_by
        is review.edited_payload
        is None
    )
    assert review.original_payload["lines"] == lines(100)
    assert entry.status == "review_required" and entry.posted_at is None
    assert entry.document.status == "bookkeeping_review_required"
    assert (entry.entry_date, entry.description) == (date(2026, 8, 1), "Receipt")
    assert [line.id for line in entry.lines] == before_ids
    assert entry.lines[0].debit_amount == entry.lines[1].credit_amount == 100
    assert db_session.query(AuditEvent).count() == 0


@pytest.mark.parametrize(
    "invalid",
    ["unknown", "inactive", "unbalanced", "subcent", "malformed", "protected", "empty"],
)
def test_edit_validation_preserves_original_journal(
    client, db_session, pending, invalid
):
    entry, review = pending
    edited = {"lines": lines(100)}
    if invalid == "unknown":
        edited["lines"][1]["account_code"] = "no-such-account"
    elif invalid == "inactive":
        entry.lines[1].account.is_active = False
    elif invalid == "unbalanced":
        edited["lines"][1]["credit_amount"] = 80
    elif invalid == "subcent":
        edited["lines"] = lines("123.001")
    elif invalid == "malformed":
        edited["lines"] = [None, "anything"]
    elif invalid == "protected":
        edited["journal_entry_id"] = str(uuid4())
    else:
        edited = {}
    db_session.commit()
    before_ids = [line.id for line in entry.lines]
    response = decision_request(client, review, "edit", edited)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "journal_validation_failed"
    db_session.expire_all()
    assert review.status == "pending" and review.edited_payload is None
    assert [line.id for line in entry.lines] == before_ids
    assert entry.posted_at is None
    assert db_session.query(ChartOfAccount).count() == 2
    assert db_session.query(AuditEvent).count() == 0


@pytest.mark.parametrize(
    ("case", "action", "code"),
    [
        ("extraction", "approve", "posting_review_required"),
        ("other_pending", "edit", "posting_review_required"),
        ("other_approval_for_old_lines", "edit", "posting_review_required"),
        ("stale_decision", "approve", "journal_not_postable"),
        ("posted", "edit", "journal_already_posted"),
        ("ambiguous", "approve", "journal_not_postable"),
        ("wrong_document", "edit", "journal_not_postable"),
        ("missing", "approve", "not_found"),
    ],
)
def test_review_checks_effective_requirements_and_linkage(
    client, db_session, pending, case, action, code
):
    entry, review = pending
    if case in {"extraction", "other_pending", "other_approval_for_old_lines"}:
        db_session.add(
            ReviewItem(
                review_type="extraction" if case == "extraction" else "bookkeeping",
                source_type="document",
                source_id=entry.document_id,
                title="Other review",
                original_payload={"lines": lines(100)},
                status="approved"
                if case == "other_approval_for_old_lines"
                else "pending",
            )
        )
    elif case == "stale_decision":
        review.original_payload = {"lines": lines(90)}
    elif case == "posted":
        entry.status = "posted"
    elif case == "missing":
        review.source_id = uuid4()
        review.original_payload = None
    else:
        review.source_type = "document"
        review.source_id = entry.document_id
        sibling = JournalEntry(
            document_id=entry.document_id if case == "ambiguous" else None,
            description="Other",
            entry_date=date.today(),
        )
        db_session.add(sibling)
        db_session.flush()
        review.original_payload = (
            {} if case == "ambiguous" else {"journal_entry_id": str(sibling.id)}
        )
    db_session.commit()
    response = decision_request(client, review, action)
    assert response.status_code == (404 if case == "missing" else 409)
    assert response.json()["error"]["code"] == code
    db_session.expire_all()
    assert review.status == "pending" and review.resolved_at is None
    assert db_session.query(AuditEvent).count() == 0


def test_legacy_document_review_selects_declared_draft(client, db_session, pending):
    entry, review = pending
    sibling = JournalEntry(
        document_id=entry.document_id, description="Other", entry_date=date.today()
    )
    db_session.add(sibling)
    entry.status = "draft"
    review.source_type = "document"
    review.source_id = entry.document_id
    db_session.commit()
    response = decision_request(client, review, "approve")
    assert response.status_code == 200
    db_session.expire_all()
    assert entry.status == "posted" and sibling.status == "draft"


@pytest.mark.parametrize(("initial", "expected"), [("approved", 200), ("posted", 409)])
def test_reject_checks_durable_journal_state(
    client, db_session, pending, initial, expected
):
    entry, review = pending
    entry.status = initial
    db_session.commit()
    response = client.post(f"/api/v1/review-items/{review.id}/reject")
    assert response.status_code == expected
    db_session.expire_all()
    if expected == 409:
        assert response.json()["error"]["code"] == "journal_already_posted"
        assert review.status == "pending" and entry.status == "posted"
        assert db_session.query(AuditEvent).count() == 0
    else:
        assert review.status == entry.status == entry.document.status == "rejected"
        assert db_session.query(AuditEvent).one().event_type == "review_item_rejected"
