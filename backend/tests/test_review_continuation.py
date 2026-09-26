"""Rollback, provenance, and sequential retries for extraction decisions."""

from contextlib import nullcontext
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session
from test_review_correction_validation import (  # noqa: F401
    bookkeeping as bookkeeping_fixture,
)
from test_review_correction_validation import (
    extraction_review as extraction_review_fixture,
)

from app.agents.schemas import BookkeepingOutcome
from app.models.audit import AuditEvent
from app.models.document import DocumentExtraction
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.services import review_continuation as service

bookkeeping = bookkeeping_fixture
extraction_review = extraction_review_fixture


@pytest.mark.parametrize("action", ["approve", "edit"])
@pytest.mark.parametrize(
    "failure",
    [
        "model_exception",
        "model_failed",
        "no_lines",
        "unbalanced",
        "persistence",
        "audit",
        "commit",
    ],
)
def test_failed_continuation_rolls_back_every_effect(
    client,
    db_session,
    extraction_review,
    bookkeeping,
    action,
    failure,
):
    doc, extraction, item = extraction_review
    outcome = bookkeeping.return_value
    if failure == "model_exception":
        bookkeeping.side_effect = RuntimeError("private provider failure")
    elif failure == "model_failed":
        bookkeeping.return_value = outcome.model_copy(update={"status": "failed"})
    elif failure == "no_lines":
        bookkeeping.return_value = BookkeepingOutcome(status="failed")
    elif failure == "unbalanced":
        outcome.journal_lines[0]["debit_amount"] = 1
    # Ensure a downstream review is also rolled back when later persistence fails.
    if failure in {"audit", "commit"}:
        outcome.needs_review = True
        outcome.status = "bookkeeping_review_required"
        outcome.risk_flags = ["low_confidence_classification"]
    target = {
        "persistence": "app.services.review_continuation.persist_bookkeeping_outcome",
        "audit": "app.services.review_continuation.log_event",
        "commit": "sqlalchemy.orm.Session.commit",
    }.get(failure)
    failure_patch = (
        patch(target, side_effect=RuntimeError("private persistence failure"))
        if target
        else nullcontext()
    )
    with failure_patch:
        response = client.post(
            f"/api/v1/review-items/{item.id}/{action}",
            json={
                "edited_payload": {"vendor_name": "Changed"},
                "resolution_note": "Test",
            }
            if action == "edit"
            else {},
        )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "review_continuation_failed"
    assert "private" not in response.text
    db_session.refresh(item)
    db_session.refresh(doc)
    db_session.refresh(extraction)
    assert item.status == "pending" and item.edited_payload is None
    assert (
        item.resolved_by is None
        and item.resolved_at is None
        and item.resolution_note is None
    )
    assert doc.status == "extraction_review_required"
    assert extraction.vendor_name == "Supplier" and extraction.status == "draft"
    assert float(extraction.confidence_score) == 0.4
    assert db_session.query(JournalEntry).count() == 0
    assert db_session.query(JournalEntryLine).count() == 0
    assert db_session.query(AuditEvent).count() == 0
    assert db_session.query(ReviewItem).count() == 1
    # Retry after the dependency recovers must succeed exactly once.
    bookkeeping.side_effect = None
    outcome.journal_lines[0]["debit_amount"] = 110
    bookkeeping.return_value = outcome
    retry = client.post(f"/api/v1/review-items/{item.id}/approve")
    assert retry.status_code == 200, retry.text
    assert db_session.query(JournalEntry).count() == 1


@pytest.mark.parametrize("winner", ["approve", "edit", "reject"])
@pytest.mark.parametrize("retry", ["approve", "edit", "reject"])
def test_resolved_decisions_return_stable_conflict(
    client,
    db_session,
    extraction_review,
    bookkeeping,
    winner,
    retry,
):
    doc, extraction, item = extraction_review
    payload = {
        "edited_payload": {"vendor_name": "Verified"},
        "resolution_note": "Original decision",
    }
    first = client.post(f"/api/v1/review-items/{item.id}/{winner}", json=payload)
    assert first.status_code == 200, first.text
    repeat = client.post(
        f"/api/v1/review-items/{item.id}/{retry}",
        json={"edited_payload": {"vendor_name": "Retry"}},
    )
    assert repeat.status_code == 409, repeat.text
    error = repeat.json()["error"]
    assert error["code"] == "review_already_resolved"
    assert error["review_status"] == first.json()["status"]
    assert error["next_workflow_status"] == (
        "rejected" if winner == "reject" else "ready_to_post"
    )
    assert bookkeeping.call_count == (0 if winner == "reject" else 1)
    assert db_session.query(AuditEvent).count() == (1 if winner == "reject" else 2)
    db_session.refresh(item)
    assert item.resolution_note == "Original decision"


def test_classification_runs_without_transaction_and_success_commits_once(
    db_session,
    extraction_review,
    bookkeeping,
):
    doc, extraction, item = extraction_review
    outcome = bookkeeping.return_value

    def classify(**kwargs):
        assert not db_session.in_transaction()
        return outcome

    bookkeeping.side_effect = classify
    with patch.object(db_session, "commit", wraps=db_session.commit) as commit:
        result = service.resolve_extraction_review(
            db=db_session,
            review_id=item.id,
            decision="edited",
            edited_payload={"vendor_name": "Verified"},
        )
    commit.assert_called_once()
    audit = (
        db_session.query(AuditEvent).filter_by(event_type="review_item_edited").one()
    )
    assert audit.input_snapshot["original_fields"]["vendor_name"] == "Supplier"
    assert audit.input_snapshot["original_extraction_id"] == str(extraction.id)
    assert audit.output_snapshot["effective_fields"]["vendor_name"] == "Verified"
    assert audit.output_snapshot["next_workflow_status"] == result.next_workflow_status


def test_changed_source_during_classification_requires_refresh(
    client,
    db_session,
    extraction_review,
    bookkeeping,
):
    doc, extraction, item = extraction_review
    extraction_id = extraction.id
    outcome = bookkeeping.return_value

    def classify(**kwargs):
        with Session(db_session.bind) as other:
            other.get(
                DocumentExtraction, extraction_id
            ).vendor_name = "Updated by another workflow"
            other.commit()
        return outcome

    bookkeeping.side_effect = classify
    response = client.post(f"/api/v1/review-items/{item.id}/approve")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "review_source_changed"
    db_session.refresh(item)
    assert item.status == "pending"
    assert db_session.query(JournalEntry).count() == 0
    assert db_session.query(AuditEvent).count() == 0


def test_new_extraction_is_rolled_back_on_audit_failure(
    client,
    db_session,
    extraction_review,
    bookkeeping,
):
    doc, extraction, item = extraction_review
    db_session.delete(extraction)
    db_session.commit()
    with patch.object(
        service, "log_event", side_effect=RuntimeError("audit unavailable")
    ):
        response = client.post(f"/api/v1/review-items/{item.id}/approve")
    assert response.status_code == 503
    assert db_session.query(DocumentExtraction).count() == 0
    assert db_session.query(JournalEntry).count() == 0


def test_rejection_rolls_back_on_commit_failure(client, db_session, extraction_review):
    doc, extraction, item = extraction_review
    with patch(
        "sqlalchemy.orm.Session.commit", side_effect=RuntimeError("commit unavailable")
    ):
        response = client.post(f"/api/v1/review-items/{item.id}/reject")
    assert response.status_code == 503
    db_session.refresh(item)
    db_session.refresh(doc)
    assert item.status == "pending" and doc.status == "extraction_review_required"
    assert db_session.query(AuditEvent).count() == 0
