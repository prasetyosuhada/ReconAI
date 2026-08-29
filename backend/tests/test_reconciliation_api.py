import uuid
from datetime import date

from app.models.journal import JournalEntry
from app.models.reconciliation import (
    BankStatementImport,
    BankTransaction,
    ReconciliationMatch,
)


def test_run_reconciliation_workflow_not_found(client):
    random_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/reconcile/run",
        json={"bank_statement_import_id": random_id},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert f"Bank statement import [{random_id}] not found." in detail


def test_run_reconciliation_workflow_success(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id,
        original_filename="bank.csv",
        status="imported",
        row_count=1,
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Office Equipment",
        amount=-500000.0,
        currency="IDR",
        status="imported",
    )
    db_session.add_all([imp, tx])
    db_session.commit()

    response = client.post(
        "/api/v1/reconcile/run",
        json={"bank_statement_import_id": str(imp_id)},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["bank_statement_import_id"] == str(imp_id)
    assert data["status"] == "matching_in_progress"


def test_list_reconciliation_matches(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id,
        original_filename="statement.csv",
        status="imported",
        row_count=1,
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Rent Expense",
        amount=-1000000.0,
        currency="IDR",
        status="matched",
    )
    match = ReconciliationMatch(
        id=uuid.uuid4(),
        bank_transaction_id=tx.id,
        match_type="exact",
        status="accepted",
        confidence_score=1.00,
        rationale="Exact amount and vendor match",
    )
    db_session.add_all([imp, tx, match])
    db_session.commit()

    response = client.get("/api/v1/reconciliation")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "accepted"


def test_accept_reconciliation_match(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id, original_filename="a.csv", status="imported", row_count=1
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Software License",
        amount=-250000.0,
        currency="IDR",
        status="imported",
    )
    match_id = uuid.uuid4()
    match = ReconciliationMatch(
        id=match_id,
        bank_transaction_id=tx.id,
        match_type="fuzzy",
        status="proposed",
        confidence_score=0.80,
    )
    db_session.add_all([imp, tx, match])
    db_session.commit()

    response = client.post(
        f"/api/v1/reconciliation/{match_id}/accept",
        json={"resolution_note": "Approved by accountant"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"

    db_session.refresh(match)
    assert match.status == "accepted"


def test_reject_reconciliation_match(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id, original_filename="b.csv", status="imported", row_count=1
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Unknown Charge",
        amount=-75000.0,
        currency="IDR",
        status="imported",
    )
    match_id = uuid.uuid4()
    match = ReconciliationMatch(
        id=match_id,
        bank_transaction_id=tx.id,
        match_type="fuzzy",
        status="proposed",
        confidence_score=0.50,
    )
    db_session.add_all([imp, tx, match])
    db_session.commit()

    response = client.post(
        f"/api/v1/reconciliation/{match_id}/reject",
        json={"resolution_note": "Does not match any transaction"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"

    db_session.refresh(match)
    assert match.status == "rejected"


def test_get_reconciliation_summary(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id, original_filename="august.csv", status="imported", row_count=2
    )
    tx1 = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Office Supplies",
        amount=150000.0,
        currency="IDR",
        status="matched",
    )
    tx2 = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 2),
        description="Bank Fee",
        amount=25000.0,
        currency="IDR",
        status="imported",
    )
    db_session.add_all([imp, tx1, tx2])
    db_session.commit()

    response = client.get(f"/api/v1/reconciliation/summary/{imp_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["bank_statement_import_id"] == str(imp_id)
    assert data["total_transactions"] == 2
    assert data["bank_statement_balance"] == 175000.0


def test_manual_match_transaction(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id, original_filename="sept.csv", status="imported", row_count=1
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 5),
        description="Client Retainer",
        amount=5000000.0,
        currency="IDR",
        status="imported",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 5),
        description="Client Payment Received",
        status="posted",
    )
    db_session.add_all([imp, tx, je])
    db_session.commit()

    response = client.post(
        "/api/v1/reconciliation/manual-match",
        json={
            "bank_transaction_id": str(tx.id),
            "journal_entry_id": str(je.id),
            "resolution_note": "Manually verified against invoice INV-009",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"

    db_session.refresh(tx)
    assert tx.status == "matched"


def test_stream_reconciliation_workflow_sse(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id, original_filename="stream_test.csv", status="imported", row_count=1
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 1),
        description="Office Equipment",
        amount=-500000.0,
        currency="IDR",
        status="imported",
    )
    je = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 1),
        description="Office Equipment",
        status="posted",
    )
    db_session.add_all([imp, tx, je])
    db_session.commit()

    response = client.get(f"/api/v1/reconciliation/stream/{imp_id}")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "data:" in response.text
