from app.agents.schemas import ProposedJournalLine
from app.services.accounting import (
    check_sensitive_accounts,
    validate_double_entry,
)


def test_validate_double_entry_valid_dict():
    lines = [
        {"debit_amount": 150000.0, "credit_amount": 0.0},
        {"debit_amount": 0.0, "credit_amount": 150000.0},
    ]
    result = validate_double_entry(lines)
    assert result.is_valid is True
    assert result.total_debit == 150000.0
    assert result.total_credit == 150000.0
    assert result.difference == 0.0
    assert len(result.errors) == 0


def test_validate_double_entry_valid_pydantic():
    lines = [
        ProposedJournalLine(
            account_code="5100",
            account_name="Expense",
            debit_amount=50000.0,
            credit_amount=0.0,
        ),
        ProposedJournalLine(
            account_code="1010",
            account_name="Bank",
            debit_amount=0.0,
            credit_amount=50000.0,
        ),
    ]
    result = validate_double_entry(lines)
    assert result.is_valid is True
    assert result.total_debit == 50000.0
    assert result.total_credit == 50000.0
    assert result.difference == 0.0


def test_validate_double_entry_unbalanced():
    lines = [
        {"debit_amount": 100000.0, "credit_amount": 0.0},
        {"debit_amount": 0.0, "credit_amount": 80000.0},
    ]
    result = validate_double_entry(lines)
    assert result.is_valid is False
    assert result.total_debit == 100000.0
    assert result.total_credit == 80000.0
    assert result.difference == 20000.0
    assert any("unbalanced" in err.lower() for err in result.errors)


def test_validate_double_entry_insufficient_lines():
    lines = [{"debit_amount": 100000.0, "credit_amount": 100000.0}]
    result = validate_double_entry(lines)
    assert result.is_valid is False
    assert any("at least 2 lines" in err.lower() for err in result.errors)


def test_validate_double_entry_negative_amount():
    lines = [
        {"debit_amount": -5000.0, "credit_amount": 0.0},
        {"debit_amount": 0.0, "credit_amount": 5000.0},
    ]
    result = validate_double_entry(lines)
    assert result.is_valid is False
    assert any("negative debit" in err.lower() for err in result.errors)


def test_validate_double_entry_compound_journal():
    lines = [
        {"debit_amount": 100000.0, "credit_amount": 0.0},  # Subtotal
        {"debit_amount": 11000.0, "credit_amount": 0.0},  # PPN Tax
        {"debit_amount": 0.0, "credit_amount": 111000.0},  # Total Payable
    ]
    result = validate_double_entry(lines)
    assert result.is_valid is True
    assert result.total_debit == 111000.0
    assert result.total_credit == 111000.0
    assert result.difference == 0.0


def test_check_sensitive_accounts_none():
    lines = [
        {"account_code": "5100", "account_name": "Office Supplies Expense"},
        {"account_code": "2000", "account_name": "Accounts Payable"},
    ]
    result = check_sensitive_accounts(lines)
    assert result.has_sensitive_account is False
    assert result.requires_human_review is False
    assert len(result.sensitive_lines) == 0
    assert len(result.risk_flags) == 0


def test_check_sensitive_accounts_bank_account():
    lines = [
        {"account_code": "5100", "account_name": "Office Supplies Expense"},
        {"account_code": "1010", "account_name": "Bank Account"},
    ]
    result = check_sensitive_accounts(lines)
    assert result.has_sensitive_account is True
    assert result.requires_human_review is True
    assert len(result.sensitive_lines) == 1
    assert result.sensitive_lines[0]["account_code"] == "1010"
    assert "uses_sensitive_account" in result.risk_flags
    assert "cash_bank_account_used" in result.risk_flags


def test_check_sensitive_accounts_suspense_account():
    lines = [
        {"account_code": "9999", "account_name": "Suspense Account"},
        {"account_code": "1000", "account_name": "Cash Account"},
    ]
    result = check_sensitive_accounts(lines)
    assert result.has_sensitive_account is True
    assert result.requires_human_review is True
    assert len(result.sensitive_lines) == 2
    assert "suspense_account_used" in result.risk_flags
    assert "cash_bank_account_used" in result.risk_flags


def test_check_sensitive_accounts_custom_coa():
    lines = [
        {"account_code": "6000", "account_name": "Owner Drawings"},
        {"account_code": "2000", "account_name": "Accounts Payable"},
    ]
    coa = [
        {"account_code": "6000", "account_name": "Owner Drawings", "is_sensitive": True}
    ]
    result = check_sensitive_accounts(lines, chart_of_accounts=coa)
    assert result.has_sensitive_account is True
    assert result.requires_human_review is True
    assert result.sensitive_lines[0]["account_code"] == "6000"
