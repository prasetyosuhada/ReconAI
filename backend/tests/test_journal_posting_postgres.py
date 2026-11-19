"""Exercise competing Ledger and Bookkeeping requests with independent DB sessions."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event

import pytest
from sqlalchemy import event, text

from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem


def seed_journal(db, *, standalone, review_source):
    document = (
        None
        if standalone
        else Document(
            original_filename="invoice.pdf",
            stored_file_path="invoice.pdf",
            mime_type="application/pdf",
            file_size_bytes=10,
            status="ready_to_post",
        )
    )
    entry = JournalEntry(
        document=document,
        entry_date=date(2026, 8, 1),
        description="Original",
        status="draft",
        source_type="manual" if standalone else "document",
    )
    for index, code in enumerate(("5100", "2000"), 1):
        account = ChartOfAccount(
            account_code=code,
            account_name=code,
            account_type="expense" if index == 1 else "liability",
            normal_balance="debit" if index == 1 else "credit",
        )
        entry.lines.append(
            JournalEntryLine(
                line_number=index,
                account=account,
                debit_amount=100 if index == 1 else 0,
                credit_amount=100 if index == 2 else 0,
            )
        )
    db.add(entry)
    db.flush()
    review = None
    if review_source:
        review = ReviewItem(
            title="Check journal",
            source_type=review_source,
            source_id=document.id if review_source == "document" else entry.id,
            review_type="bookkeeping",
            status="pending",
            original_payload={"journal_entry_id": str(entry.id)},
        )
        db.add(review)
    db.commit()
    return entry.id, review.id if review else None


def request_action(client, action, journal_id, review_id):
    if action == "post":
        return client.post(f"/api/v1/ledger/journal-entries/{journal_id}/post")
    body = {"resolution_note": action}
    if action == "edit":
        body["edited_payload"] = {
            "description": "Corrected",
            "lines": [
                {"account_code": "5100", "debit_amount": 120},
                {"account_code": "2000", "credit_amount": 120},
            ],
        }
    return client.post(f"/api/v1/review-items/{review_id}/{action}", json=body)


def wait_for_row_lock(sessions, schema, table):
    # Observe the actual blocking backend before releasing the winning request.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with sessions() as db:
            waiting = (
                db.execute(
                    text("""
                SELECT query FROM pg_stat_activity
                WHERE application_name = :schema AND wait_event_type = 'Lock'
                  AND cardinality(pg_blocking_pids(pid)) > 0
            """),
                    {"schema": schema},
                )
                .scalars()
                .all()
            )
        if any(f"FROM {table}" in query for query in waiting):
            return
        time.sleep(0.02)
    pytest.fail(f"The competing request did not wait on {table}")


@pytest.mark.parametrize(
    ("winner", "loser", "source", "standalone", "conflict"),
    [
        ("post", "post", None, False, "journal_already_posted"),
        ("post", "post", None, True, "journal_already_posted"),
        ("approve", "edit", "journal_entry", False, "review_already_resolved"),
        ("edit", "reject", "document", False, "review_already_resolved"),
        ("reject", "approve", "document", False, "review_already_resolved"),
        ("approve", "post", "journal_entry", False, "journal_already_posted"),
        ("reject", "post", "journal_entry", False, "journal_not_postable"),
    ],
)
def test_waiter_observes_committed_decision(
    pg_api, winner, loser, source, standalone, conflict
):
    client, sessions, schema = pg_api
    with sessions() as db:
        ids = seed_journal(db, standalone=standalone, review_source=source)

    locked, release = Event(), Event()

    def hold_first_commit(session):
        locked.set()
        assert release.wait(timeout=10)

    event.listen(sessions, "before_commit", hold_first_commit)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(request_action, client, winner, *ids)
            try:
                assert locked.wait(timeout=5)
                second = pool.submit(request_action, client, loser, *ids)
                wait_for_row_lock(
                    sessions, schema, "journal_entries" if standalone else "documents"
                )
            finally:
                release.set()
            success, blocked = first.result(timeout=15), second.result(timeout=15)
    finally:
        event.remove(sessions, "before_commit", hold_first_commit)

    assert success.status_code == 200, success.text
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == conflict
    with sessions() as db:
        entry = db.get(JournalEntry, ids[0])
        posted_at = entry.posted_at
        expected_status = "rejected" if winner == "reject" else "posted"
        assert entry.status == expected_status
        assert (posted_at is None) == (winner == "reject")
        if entry.document:
            assert entry.document.status == expected_status
        if source:
            decision = {"approve": "approved", "edit": "edited", "reject": "rejected"}[
                winner
            ]
            assert db.get(ReviewItem, ids[1]).status == decision
        assert entry.description == ("Corrected" if winner == "edit" else "Original")
        assert (
            entry.lines[0].debit_amount
            == entry.lines[1].credit_amount
            == (120 if winner == "edit" else 100)
        )

    replay = request_action(client, winner, *ids)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == (
        "review_already_resolved" if source else "journal_already_posted"
    )
    with sessions() as db:
        assert db.get(JournalEntry, ids[0]).posted_at == posted_at
        events = db.query(AuditEvent).order_by(AuditEvent.created_at).all()
        expected = [f"review_item_{decision}"] if source else []
        if winner != "reject":
            expected.append("journal_entry_posted")
        assert [e.event_type for e in events] == expected


def test_waiting_reject_rechecks_review_link(pg_api):
    client, sessions, schema = pg_api
    with sessions() as db:
        journal_id, review_id = seed_journal(
            db, standalone=True, review_source="journal_entry"
        )
        sibling = JournalEntry(
            entry_date=date(2026, 8, 1), description="Sibling", source_type="manual"
        )
        db.add(sibling)
        db.commit()
        sibling_id = sibling.id

    with sessions() as updater, ThreadPoolExecutor(max_workers=1) as pool:
        review = updater.get(ReviewItem, review_id, with_for_update=True)
        waiting = pool.submit(request_action, client, "reject", journal_id, review_id)
        try:
            wait_for_row_lock(sessions, schema, "review_items")
            review.source_id = sibling_id
            review.original_payload = {"journal_entry_id": str(sibling_id)}
            updater.commit()
        finally:
            updater.rollback()
        response = waiting.result(timeout=15)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "journal_not_postable"
    with sessions() as db:
        assert db.get(ReviewItem, review_id).status == "pending"
        assert (
            db.get(JournalEntry, journal_id).status
            == db.get(JournalEntry, sibling_id).status
            == "draft"
        )
        assert db.query(AuditEvent).count() == 0
