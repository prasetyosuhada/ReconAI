"""End-to-End (E2E) Validation Failure & Accounting Guardrail Integration Test.

Tests Skenario Gagal Validasi:
1. LLM / User creates unbalanced Journal Entry (Total Debits != Total Credits).
2. Deterministic backend rule-based engine rejects invalid journal entry before saving/posting.
3. System prevents posting unbalanced entries to General Ledger.
4. Sensitive account guardrails force human review routing.
"""

import uuid
from datetime import date

from app.models.coa import ChartOfAccount
from app.models.journal import JournalEntry, JournalEntryLine
from app.services.accounting import (
    check_sensitive_accounts,
    post_journal_entry_to_ledger,
    validate_double_entry,
)


def seed_coa_accounts(db):
    """Seed essential Chart of Accounts for testing."""
    accounts = [
        ChartOfAccount(
            account_code="1000",
            account_name="Cash & Bank",
            account_type="asset",
            normal_balance="debit",
            is_sensitive=True,  # Cash is sensitive account requiring review
            is_active=True,
        ),
        ChartOfAccount(
            account_code="2000",
            account_name="Accounts Payable",
            account_type="liability",
            normal_balance="credit",
            is_sensitive=False,
            is_active=True,
        ),
        ChartOfAccount(
            account_code="5100",
            account_name="Software Subscriptions",
            account_type="expense",
            normal_balance="debit",
            is_sensitive=False,
            is_active=True,
        ),
    ]
    for acc in accounts:
        db.add(acc)
    db.commit()


def test_unbalanced_journal_entry_rejection(db_session):
    """Verify backend deterministically rejects unbalanced journal entry (Debits != Credits)."""
    seed_coa_accounts(db_session)

    acc_5100 = db_session.query(ChartOfAccount).filter(ChartOfAccount.account_code == "5100").first()
    acc_2000 = db_session.query(ChartOfAccount).filter(ChartOfAccount.account_code == "2000").first()

    # Create Unbalanced Journal Entry: Debit 1,500,000 vs Credit 1,200,000 (Difference: 300,000)
    unbalanced_je = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 12),
        description="Unbalanced Faulty LLM Journal Suggestion Test",
        status="draft",
        agent_name="Bookkeeping Agent",
        confidence_score=0.90,
    )
    db_session.add(unbalanced_je)

    line_debit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=unbalanced_je.id,
        line_number=1,
        account_id=acc_5100.id,
        debit_amount=1500000.0,
        credit_amount=0.0,
        description="Software Subscription Expense",
    )
    line_credit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=unbalanced_je.id,
        line_number=2,
        account_id=acc_2000.id,
        debit_amount=0.0,
        credit_amount=1200000.0,  # Unbalanced credit (1.2M vs 1.5M)
        description="Accounts Payable Faulty Amount",
    )
    db_session.add(line_debit)
    db_session.add(line_credit)
    db_session.commit()

    # 1. Test Deterministic Double-Entry Validation Rule
    val_result = validate_double_entry(unbalanced_je.lines)
    assert val_result.is_valid is False
    assert val_result.total_debit == 1500000.0
    assert val_result.total_credit == 1200000.0
    assert val_result.difference == 300000.0
    assert len(val_result.errors) >= 1
    assert any("equal" in err.lower() or "unbalanced" in err.lower() or "difference" in err.lower() for err in val_result.errors)

    # 2. Test Ledger Posting Guardrail Rejection
    post_res = post_journal_entry_to_ledger(unbalanced_je, db_session)
    assert post_res.success is False
    assert len(post_res.errors) >= 1

    # Verify Journal Entry status remained draft (NOT posted)
    assert unbalanced_je.status != "posted"
    print("\n✅ Deterministic Unbalanced Journal Entry Rejection Test Passed!")


def test_sensitive_account_guardrail_check(db_session):
    """Verify sensitive account guardrail flags Cash transaction for human review."""
    acc_1000 = db_session.query(ChartOfAccount).filter(ChartOfAccount.account_code == "1000").first()
    if not acc_1000:
        seed_coa_accounts(db_session)
        acc_1000 = db_session.query(ChartOfAccount).filter(ChartOfAccount.account_code == "1000").first()

    acc_5100 = db_session.query(ChartOfAccount).filter(ChartOfAccount.account_code == "5100").first()

    sensitive_je = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 8, 12),
        description="Petty Cash Disbursement for Software",
        status="draft",
    )

    line_debit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=sensitive_je.id,
        line_number=1,
        account_id=acc_5100.id,
        debit_amount=250000.0,
        credit_amount=0.0,
    )
    line_credit = JournalEntryLine(
        id=uuid.uuid4(),
        journal_entry_id=sensitive_je.id,
        line_number=2,
        account_id=acc_1000.id,
        debit_amount=0.0,
        credit_amount=250000.0,
    )
    sensitive_je.lines.extend([line_debit, line_credit])

    # Perform sensitive account check
    check_res = check_sensitive_accounts([
        {"account_code": "5100", "debit_amount": 250000.0, "credit_amount": 0.0},
        {"account_code": "1000", "debit_amount": 0.0, "credit_amount": 250000.0},
    ], db_session)

    assert check_res.has_sensitive_account is True
    assert check_res.requires_human_review is True
    assert len(check_res.risk_flags) >= 1
    print("\n✅ Sensitive Account Routing Guardrail Test Passed!")
