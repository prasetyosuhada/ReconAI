from app.agents.schemas import ProposedJournalLine
from app.services.accounting import (
    check_sensitive_accounts,
    find_exact_reconciliation_matches,
    post_journal_entry_to_ledger,
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


def test_find_exact_reconciliation_matches_success():
    bank_tx = {
        "amount": -111000.0,
        "transaction_date": "2026-08-05",
        "description": "TOKO GRAMEDIA JAKARTA",
    }
    candidates = [
        {
            "id": "je-101",
            "entry_date": "2026-08-03",  # 2 days diff (<= 3 days)
            "description": "Toko Gramedia Stationary",
            "total_debit": 111000.0,
        },
        {
            "id": "je-102",
            "entry_date": "2026-08-05",
            "description": "Indomaret Snacks",
            "total_debit": 50000.0,
        },
    ]

    result = find_exact_reconciliation_matches(bank_tx, candidates)
    assert result.is_exact_match is True
    assert result.confidence_score == 1.00
    assert result.matched_entry_id == "je-101"
    assert result.match_details["amount_matched"] is True
    assert result.match_details["date_matched"] is True
    assert result.match_details["vendor_matched"] is True


def test_find_exact_reconciliation_matches_date_out_of_window():
    bank_tx = {
        "amount": -111000.0,
        "transaction_date": "2026-08-15",
        "description": "TOKO GRAMEDIA JAKARTA",
    }
    candidates = [
        {
            "id": "je-101",
            "entry_date": "2026-08-01",  # 14 days diff (> 3 days)
            "description": "Toko Gramedia Stationary",
            "total_debit": 111000.0,
        }
    ]

    result = find_exact_reconciliation_matches(bank_tx, candidates)
    assert result.is_exact_match is False
    assert result.confidence_score == 0.00
    assert result.matched_entry_id is None


def test_find_exact_reconciliation_matches_amount_mismatch():
    bank_tx = {
        "amount": -120000.0,
        "transaction_date": "2026-08-05",
        "description": "TOKO GRAMEDIA JAKARTA",
    }
    candidates = [
        {
            "id": "je-101",
            "entry_date": "2026-08-05",
            "description": "Toko Gramedia Stationary",
            "total_debit": 111000.0,
        }
    ]

    result = find_exact_reconciliation_matches(bank_tx, candidates)
    assert result.is_exact_match is False
    assert result.confidence_score == 0.00


def test_post_journal_entry_to_ledger_success():
    entry = {
        "id": "je-201",
        "status": "draft",
        "lines": [
            {"debit_amount": 75000.0, "credit_amount": 0.0},
            {"debit_amount": 0.0, "credit_amount": 75000.0},
        ],
    }
    result = post_journal_entry_to_ledger(entry)
    assert result.success is True
    assert result.status == "posted"
    assert result.posted_at is not None
    assert entry["status"] == "posted"


def test_post_journal_entry_to_ledger_already_posted():
    entry = {
        "id": "je-202",
        "status": "posted",
        "lines": [
            {"debit_amount": 75000.0, "credit_amount": 0.0},
            {"debit_amount": 0.0, "credit_amount": 75000.0},
        ],
    }
    result = post_journal_entry_to_ledger(entry)
    assert result.success is False
    assert any("already posted" in err for err in result.errors)


def test_post_journal_entry_to_ledger_voided():
    entry = {
        "id": "je-203",
        "status": "voided",
        "lines": [],
    }
    result = post_journal_entry_to_ledger(entry)
    assert result.success is False
    assert any("Cannot post a voided" in err for err in result.errors)


def test_post_journal_entry_to_ledger_unbalanced_rejection():
    entry = {
        "id": "je-204",
        "status": "draft",
        "lines": [
            {"debit_amount": 100000.0, "credit_amount": 0.0},
            {"debit_amount": 0.0, "credit_amount": 50000.0},  # Unbalanced
        ],
    }
    result = post_journal_entry_to_ledger(entry)
    assert result.success is False
    assert any("validation failed" in err.lower() for err in result.errors)
