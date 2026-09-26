"""Real row-lock tests. Set RECONAI_TEST_POSTGRES_URL to a PostgreSQL test connection.

Each test owns a randomly named schema; application tables are never recreated or
cleared. Only that test's schema is dropped on exit. LLM calls are stubbed.
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agents.schemas import BookkeepingOutcome
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditEvent
from app.models.coa import ChartOfAccount
from app.models.document import Document, DocumentExtraction
from app.models.journal import JournalEntry, JournalEntryLine
from app.models.review import ReviewItem
from app.services import review_continuation as service


@pytest.fixture
def pg_review():
    url = os.environ.get("RECONAI_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set RECONAI_TEST_POSTGRES_URL to run PostgreSQL race tests.")
    admin = create_engine(url, connect_args={"connect_timeout": 5})
    assert admin.dialect.name == "postgresql"
    schema = "test_review_" + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={
            "options": f"-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=15000",
            "application_name": schema,
        },
    )
    sessions = sessionmaker(bind=engine, autoflush=False)
    previous = app.dependency_overrides.get(get_db)

    def get_test_db():
        with sessions() as db:
            yield db

    try:
        Base.metadata.create_all(engine)
        with sessions() as db:
            doc = Document(
                id=uuid.uuid4(),
                original_filename="test.pdf",
                stored_file_path="/tmp/test.pdf",
                mime_type="application/pdf",
                file_size_bytes=1,
                document_type="invoice",
                status="extraction_review_required",
            )
            extraction = DocumentExtraction(
                id=uuid.uuid4(),
                document_id=doc.id,
                vendor_name="Original",
                transaction_date=date(2026, 9, 25),
                subtotal_amount=100,
                tax_amount=10,
                total_amount=110,
                currency="IDR",
                line_items=[],
                confidence_score=0.5,
                provider_metadata={"warnings": ["Original evidence"]},
                status="draft",
            )
            review = ReviewItem(
                id=uuid.uuid4(),
                review_type="extraction",
                source_type="document",
                source_id=doc.id,
                status="pending",
                title="Review",
                original_payload={"vendor_name": "Original"},
            )
            db.add_all(
                [
                    doc,
                    extraction,
                    review,
                    ChartOfAccount(
                        account_code="5100",
                        account_name="Expense",
                        account_type="expense",
                        normal_balance="debit",
                        is_active=True,
                    ),
                    ChartOfAccount(
                        account_code="2000",
                        account_name="Payable",
                        account_type="liability",
                        normal_balance="credit",
                        is_active=True,
                    ),
                ]
            )
            db.commit()
            ids = doc.id, extraction.id, review.id
        app.dependency_overrides[get_db] = get_test_db
        with TestClient(app) as client:
            yield client, sessions, ids, schema
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _outcome():
    return BookkeepingOutcome(
        status="bookkeeping_review_required",
        needs_review=True,
        risk_flags=["low_confidence_classification"],
        confidence_score=0.7,
        is_balanced=True,
        total_debit=110,
        total_credit=110,
        entry_date="2026-09-25",
        journal_lines=[
            dict(
                account_code="5100",
                account_name="Expense",
                debit_amount=110,
                credit_amount=0,
            ),
            dict(
                account_code="2000",
                account_name="Payable",
                debit_amount=0,
                credit_amount=110,
            ),
        ],
    )


@pytest.mark.parametrize(
    "actions", [("approve", "approve"), ("edit", "edit"), ("approve", "edit")]
)
def test_concurrent_decisions_have_one_winner_and_real_row_lock(pg_review, actions):
    client, sessions, (doc_id, extraction_id, review_id), schema = pg_review
    classified = Barrier(2)
    winner_locked = Event()
    release = Event()
    persist = service._persist_extraction

    def classify(**kwargs):
        classified.wait(timeout=10)
        return _outcome()

    def hold_winner(*args, **kwargs):
        winner_locked.set()
        assert release.wait(timeout=10)
        return persist(*args, **kwargs)

    def submit(action, vendor):
        return client.post(
            f"/api/v1/review-items/{review_id}/{action}",
            json={"edited_payload": {"vendor_name": vendor}},
        )

    with (
        patch.object(service, "classify_bookkeeping", side_effect=classify),
        patch.object(service, "_persist_extraction", side_effect=hold_winner) as save,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [
            pool.submit(submit, action, f"Vendor {index}")
            for index, action in enumerate(actions)
        ]
        try:
            assert winner_locked.wait(timeout=10)
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline:
                with sessions() as db:
                    blocked = (
                        db.execute(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock'"
                            ),
                            {"name": schema},
                        ).scalar()
                        > 0
                    )
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "The losing PostgreSQL session must wait on the row lock."
        finally:
            release.set()
        responses = [future.result(timeout=15) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(
        response.json()["error"]
        for response in responses
        if response.status_code == 409
    )
    assert conflict["code"] == "review_already_resolved"
    assert conflict["next_workflow_status"] == "bookkeeping_review_required"
    assert save.call_count == 1
    with sessions() as db:
        assert db.query(JournalEntry).count() == 1
        assert db.query(JournalEntryLine).count() == 2
        assert db.query(ReviewItem).filter_by(review_type="bookkeeping").count() == 1
        assert db.query(AuditEvent).count() == 2
        assert db.get(Document, doc_id).status == "bookkeeping_review_required"
        assert db.get(DocumentExtraction, extraction_id).provider_metadata == {
            "warnings": ["Original evidence"]
        }
        audit = db.query(AuditEvent).filter(AuditEvent.actor_type == "human").one()
        assert (
            audit.output_snapshot["effective_fields"]["vendor_name"]
            == db.get(DocumentExtraction, extraction_id).vendor_name
        )


@pytest.mark.parametrize("action", ["approve", "edit"])
@pytest.mark.parametrize("model_result", ["success", "failed", "exception"])
def test_rejection_wins_while_model_call_is_in_flight(pg_review, action, model_result):
    client, sessions, (doc_id, extraction_id, review_id), _ = pg_review
    entered, release = Event(), Event()

    def classify(**kwargs):
        entered.set()
        assert release.wait(timeout=10)
        if model_result == "exception":
            raise RuntimeError("Provider failed after another reviewer rejected")
        if model_result == "failed":
            return BookkeepingOutcome(status="failed")
        return _outcome()

    with (
        patch.object(service, "classify_bookkeeping", side_effect=classify),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        future = pool.submit(
            client.post,
            f"/api/v1/review-items/{review_id}/{action}",
            json={"edited_payload": {"vendor_name": "Changed"}},
        )
        try:
            assert entered.wait(timeout=10)
            rejected = client.post(f"/api/v1/review-items/{review_id}/reject")
            assert rejected.status_code == 200
        finally:
            release.set()
        response = future.result(timeout=15)
    assert response.status_code == 409
    assert response.json()["error"]["review_status"] == "rejected"
    with sessions() as db:
        assert db.get(Document, doc_id).status == "rejected"
        assert db.get(DocumentExtraction, extraction_id).vendor_name == "Original"
        assert db.query(JournalEntry).count() == 0
        assert db.query(AuditEvent).count() == 1


def test_postgres_rolls_back_after_downstream_and_first_audit_flush(pg_review):
    client, sessions, (doc_id, extraction_id, review_id), _ = pg_review
    audit = service.log_event

    def fail_second_audit(**kwargs):
        if kwargs["event_type"] == "bookkeeping_completed":
            kwargs["db"].flush()
            raise RuntimeError("Injected audit failure")
        return audit(**kwargs)

    with (
        patch.object(service, "classify_bookkeeping", return_value=_outcome()),
        patch.object(service, "log_event", side_effect=fail_second_audit),
    ):
        response = client.post(
            f"/api/v1/review-items/{review_id}/edit",
            json={"edited_payload": {"vendor_name": "Changed"}},
        )
    assert response.status_code == 503
    with sessions() as db:
        assert db.get(ReviewItem, review_id).status == "pending"
        assert db.get(Document, doc_id).status == "extraction_review_required"
        assert db.get(DocumentExtraction, extraction_id).vendor_name == "Original"
        assert db.get(DocumentExtraction, extraction_id).status == "draft"
        assert db.query(JournalEntry).count() == 0
        assert db.query(JournalEntryLine).count() == 0
        assert db.query(ReviewItem).count() == 1
        assert db.query(AuditEvent).count() == 0
