import io
import uuid
from datetime import date

from app.models.audit import AuditEvent
from app.models.reconciliation import BankStatementImport, BankTransaction


def test_upload_bank_statement_csv_success(client, db_session):
    csv_data = (
        "transaction_date,description,amount,currency,reference_number\n"
        "2026-08-01,Gramedia Book Store,-150000.00,IDR,REF-001\n"
        "2026-08-02,Client Payment,5000000.00,IDR,REF-002\n"
    )
    file = ("mutasi_bank.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")

    response = client.post("/api/v1/bank/upload-mock", files={"file": file})

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["original_filename"] == "mutasi_bank.csv"
    assert data["row_count"] == 2
    assert data["status"] == "imported"
    assert "links" in data

    # Verify DB records created
    import_id = uuid.UUID(data["id"])
    imp = (
        db_session.query(BankStatementImport)
        .filter(BankStatementImport.id == import_id)
        .first()
    )
    assert imp is not None
    assert len(imp.transactions) == 2

    # Verify AuditEvent recorded
    audit = (
        db_session.query(AuditEvent).filter(AuditEvent.source_id == import_id).first()
    )
    assert audit is not None
    assert audit.event_type == "bank_statement_imported"


def test_upload_bank_statement_invalid_extension(client):
    file = ("statement.txt", io.BytesIO(b"dummy text"), "text/plain")
    response = client.post("/api/v1/bank/upload-mock", files={"file": file})

    assert response.status_code == 400
    assert "Only CSV files are supported" in response.json()["detail"]


def test_upload_bank_statement_empty_csv(client):
    file = ("empty.csv", io.BytesIO(b""), "text/csv")
    response = client.post("/api/v1/bank/upload-mock", files={"file": file})

    assert response.status_code == 400
    assert "CSV file is empty" in response.json()["detail"]


def test_list_bank_statement_imports(client, db_session):
    imp1 = BankStatementImport(
        id=uuid.uuid4(),
        original_filename="july.csv",
        status="imported",
        row_count=5,
    )
    imp2 = BankStatementImport(
        id=uuid.uuid4(),
        original_filename="august.csv",
        status="imported",
        row_count=10,
    )
    db_session.add_all([imp1, imp2])
    db_session.commit()

    response = client.get("/api/v1/bank-statements")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_bank_statement_transactions(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id,
        original_filename="september.csv",
        status="imported",
        row_count=1,
    )
    tx = BankTransaction(
        id=uuid.uuid4(),
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 5),
        description="Software Subscription",
        amount=-299000.0,
        currency="IDR",
        reference_number="REF-999",
        status="imported",
    )
    db_session.add_all([imp, tx])
    db_session.commit()

    response = client.get(f"/api/v1/bank-statements/{imp_id}/transactions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["description"] == "Software Subscription"
    assert data["items"][0]["amount"] == -299000.0


def test_get_single_bank_transaction(client, db_session):
    imp_id = uuid.uuid4()
    imp = BankStatementImport(
        id=imp_id,
        original_filename="october.csv",
        status="imported",
        row_count=1,
    )
    tx_id = uuid.uuid4()
    tx = BankTransaction(
        id=tx_id,
        bank_statement_import_id=imp_id,
        transaction_date=date(2026, 8, 10),
        description="Hosting Service",
        amount=-500000.0,
        currency="IDR",
        reference_number="REF-100",
        status="imported",
    )
    db_session.add_all([imp, tx])
    db_session.commit()

    response = client.get(f"/api/v1/bank-statements/transactions/{tx_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(tx_id)
    assert data["description"] == "Hosting Service"
    assert data["amount"] == -500000.0
