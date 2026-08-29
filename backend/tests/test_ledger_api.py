import uuid
from datetime import date

from app.models.coa import ChartOfAccount
from app.models.journal import JournalEntry, JournalEntryLine


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


def test_post_journal_entry_success(client, db_session):
    je_id = uuid.uuid4()
    coa1_id = uuid.uuid4()
    coa2_id = uuid.uuid4()

    coa1 = ChartOfAccount(
        id=coa1_id,
        account_code="5100",
        account_name="Expense",
        account_type="expense",
        normal_balance="debit",
    )
    coa2 = ChartOfAccount(
        id=coa2_id,
        account_code="1010",
        account_name="Bank",
        account_type="asset",
        normal_balance="debit",
    )
    je = JournalEntry(
        id=je_id,
        entry_date=date(2026, 8, 1),
        description="Draft Entry",
        status="approved",
    )
    line1 = JournalEntryLine(
        journal_entry_id=je_id,
        account_id=coa1_id,
        line_number=1,
        debit_amount=100000.0,
        credit_amount=0.0,
    )
    line2 = JournalEntryLine(
        journal_entry_id=je_id,
        account_id=coa2_id,
        line_number=2,
        debit_amount=0.0,
        credit_amount=100000.0,
    )
    db_session.add_all([coa1, coa2, je, line1, line2])
    db_session.commit()

    response = client.post(f"/api/v1/ledger/journal-entries/{je_id}/post")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "posted"
    assert data["trial_balance_status"] == "balanced"

    db_session.refresh(je)
    assert je.status == "posted"


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
