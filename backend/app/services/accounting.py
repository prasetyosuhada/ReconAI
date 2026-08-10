"""Deterministic Accounting Engine for ReconAI.

Provides rule-based validation logic for double-entry bookkeeping, trial balance,
and ledger posting guardrails.
"""

import logging
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DoubleEntryValidationResult(BaseModel):
    """Structured result returned by double-entry validation."""

    is_valid: bool = Field(
        ..., description="True if total debits equal total credits and lines are valid"
    )
    total_debit: float = Field(..., description="Sum of debit amounts")
    total_credit: float = Field(..., description="Sum of credit amounts")
    difference: float = Field(
        ..., description="Absolute difference between debit and credit sums"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of validation errors if invalid"
    )


class SensitiveAccountCheckResult(BaseModel):
    """Structured result returned by sensitive account checking."""

    has_sensitive_account: bool = Field(
        ..., description="True if any sensitive account was referenced in lines"
    )
    requires_human_review: bool = Field(
        ..., description="True if human review is mandatory due to sensitive accounts"
    )
    sensitive_lines: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Details of lines referencing sensitive accounts",
    )
    risk_flags: list[str] = Field(
        default_factory=list, description="List of triggered risk flags"
    )


class ExactMatchResult(BaseModel):
    """Structured result returned by exact reconciliation matching."""

    is_exact_match: bool = Field(
        ..., description="True if a single deterministic exact match is found"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Match confidence score (1.00 for exact match)",
    )
    matched_entry_id: str | None = Field(
        default=None, description="ID of the exact matched journal entry if found"
    )
    match_details: dict[str, Any] | None = Field(
        default=None, description="Metadata details of the exact match"
    )
    evaluated_candidates: list[dict[str, Any]] = Field(
        default_factory=list, description="List of evaluated candidate matches"
    )


class PostToLedgerResult(BaseModel):
    """Structured result returned by post_journal_entry_to_ledger."""

    success: bool = Field(
        ..., description="True if journal entry was successfully posted to ledger"
    )
    journal_entry_id: str = Field(..., description="ID of the journal entry")
    status: str = Field(..., description="Updated status of the journal entry")
    posted_at: str | None = Field(
        default=None, description="ISO timestamp when the entry was posted"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of errors if posting failed"
    )


class UnbalancedJournalEntryError(Exception):
    """Exception raised when an unbalanced journal entry save is attempted."""

    def __init__(self, validation_result: DoubleEntryValidationResult):
        self.validation_result = validation_result
        err_msg = "; ".join(validation_result.errors)
        super().__init__(f"Cannot save unbalanced journal entry: {err_msg}")


class SaveJournalEntryResult(BaseModel):
    """Structured result returned by save_journal_entry_safely."""

    success: bool = Field(
        ..., description="True if journal entry passed validation and was saved"
    )
    journal_entry_id: str | None = Field(
        default=None, description="ID of the created/updated journal entry"
    )
    status: str = Field(..., description="Final status assigned to journal entry")
    validation_result: DoubleEntryValidationResult = Field(
        ..., description="Double-entry balance validation output"
    )
    sensitive_check_result: SensitiveAccountCheckResult = Field(
        ..., description="Sensitive account inspection output"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of errors if saving failed"
    )


def _to_decimal(val: Any) -> Decimal:
    """Helper to convert float/int/str/Decimal safely to Decimal (2 decimals)."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_string(s: str | None) -> str:
    """Normalize string by converting to lowercase and stripping special chars."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _vendor_strings_match(s1: str | None, s2: str | None) -> bool:
    """Check if two vendor/description strings match using normalized token overlap."""
    if not s1 or not s2:
        return False
    norm1 = _normalize_string(s1)
    norm2 = _normalize_string(s2)
    if not norm1 or not norm2:
        return False

    if norm1 in norm2 or norm2 in norm1:
        return True

    words1 = {w for w in re.findall(r"[a-z0-9]+", s1.lower()) if len(w) >= 3}
    words2 = {w for w in re.findall(r"[a-z0-9]+", s2.lower()) if len(w) >= 3}

    if not words1 or not words2:
        return False

    common = words1.intersection(words2)
    return len(common) > 0


def validate_double_entry(
    lines: Sequence[Any],
    tolerance: float = 0.01,
) -> DoubleEntryValidationResult:
    """Validate that a set of journal lines satisfies double-entry accounting rules.

    Rules:
    1. Minimum of 2 lines required.
    2. At least one line with non-zero debit and one line with non-zero credit.
    3. All debit and credit amounts must be non-negative (>= 0.00).
    4. Sum of debits MUST equal sum of credits (within specified tolerance).

    Args:
        lines: Sequence of line objects (dicts, Pydantic models, or ORM objects)
            containing `debit_amount` and `credit_amount`.
        tolerance: Allowed floating point difference threshold (default 0.01).

    Returns:
        DoubleEntryValidationResult detailing validity, totals, difference, and errors.
    """
    errors: list[str] = []

    if not lines or len(lines) < 2:
        errors.append("Double-entry journal must contain at least 2 lines.")

    total_debit_dec = Decimal("0.00")
    total_credit_dec = Decimal("0.00")
    has_positive_debit = False
    has_positive_credit = False

    for idx, line in enumerate(lines or []):
        if isinstance(line, dict):
            debit_raw = line.get("debit_amount", 0.0)
            credit_raw = line.get("credit_amount", 0.0)
        else:
            debit_raw = getattr(line, "debit_amount", 0.0)
            credit_raw = getattr(line, "credit_amount", 0.0)

        try:
            debit_dec = _to_decimal(debit_raw)
            credit_dec = _to_decimal(credit_raw)
        except Exception:
            errors.append(f"Line #{idx + 1}: Invalid numeric format for debit/credit.")
            continue

        if debit_dec < Decimal("0.00"):
            errors.append(f"Line #{idx + 1}: Negative debit is invalid.")
        if credit_dec < Decimal("0.00"):
            errors.append(f"Line #{idx + 1}: Negative credit is invalid.")

        if debit_dec > Decimal("0.00"):
            has_positive_debit = True
        if credit_dec > Decimal("0.00"):
            has_positive_credit = True

        total_debit_dec += debit_dec
        total_credit_dec += credit_dec

    if lines and len(lines) >= 2:
        if not has_positive_debit:
            errors.append("Journal entry must have at least one line with debit > 0.")
        if not has_positive_credit:
            errors.append("Journal entry must have at least one line with credit > 0.")

    diff_dec = abs(total_debit_dec - total_credit_dec)
    tolerance_dec = Decimal(str(tolerance))

    if diff_dec > tolerance_dec:
        errors.append(
            f"Journal entry is unbalanced: Total Debits ({total_debit_dec:.2f}) != "
            f"Total Credits ({total_credit_dec:.2f}), difference = {diff_dec:.2f}."
        )

    is_valid = len(errors) == 0

    return DoubleEntryValidationResult(
        is_valid=is_valid,
        total_debit=float(total_debit_dec),
        total_credit=float(total_credit_dec),
        difference=float(diff_dec),
        errors=errors,
    )


def check_sensitive_accounts(
    lines: Sequence[Any],
    chart_of_accounts: Sequence[Any] | None = None,
) -> SensitiveAccountCheckResult:
    """Check if any journal entry line touches a sensitive account.

    Sensitive accounts include:
    - Cash Account (1000)
    - Bank Account (1010)
    - Tax Payable / PPN (2100)
    - Owner Equity / Capital (3000)
    - Suspense Account (9999)
    - Any account with `is_sensitive=True` in Chart of Accounts.

    Args:
        lines: Sequence of line dicts, Pydantic models, or ORM objects.
        chart_of_accounts: Optional sequence of COA dicts or ORM objects.

    Returns:
        SensitiveAccountCheckResult containing details and risk flags.
    """
    sensitive_codes: set[str] = {"1000", "1010", "2100", "3000", "9999"}
    coa_map: dict[str, dict[str, Any]] = {}

    if chart_of_accounts:
        for coa in chart_of_accounts:
            if isinstance(coa, dict):
                code = str(coa.get("account_code", ""))
                is_sens = bool(coa.get("is_sensitive", False))
                name = coa.get("account_name", "")
            else:
                code = str(getattr(coa, "account_code", ""))
                is_sens = bool(getattr(coa, "is_sensitive", False))
                name = getattr(coa, "account_name", "")

            if code:
                coa_map[code] = {"is_sensitive": is_sens, "name": name}
                if is_sens:
                    sensitive_codes.add(code)

    sensitive_lines: list[dict[str, Any]] = []
    risk_flags: set[str] = set()

    for idx, line in enumerate(lines or []):
        if isinstance(line, dict):
            code = str(line.get("account_code", ""))
            name = line.get("account_name", "")
            debit = float(line.get("debit_amount", 0.0))
            credit = float(line.get("credit_amount", 0.0))
        else:
            code = str(getattr(line, "account_code", ""))
            name = getattr(line, "account_name", "")
            debit = float(getattr(line, "debit_amount", 0.0))
            credit = float(getattr(line, "credit_amount", 0.0))

        is_sensitive = code in sensitive_codes or coa_map.get(code, {}).get(
            "is_sensitive", False
        )

        if is_sensitive:
            sensitive_lines.append(
                {
                    "line_index": idx,
                    "account_code": code,
                    "account_name": name or coa_map.get(code, {}).get("name", ""),
                    "debit_amount": debit,
                    "credit_amount": credit,
                }
            )
            risk_flags.add("uses_sensitive_account")

            if code in ("1000", "1010"):
                risk_flags.add("cash_bank_account_used")
            if code == "9999":
                risk_flags.add("suspense_account_used")
            if code == "2100":
                risk_flags.add("tax_payable_account_used")

    has_sensitive = len(sensitive_lines) > 0

    return SensitiveAccountCheckResult(
        has_sensitive_account=has_sensitive,
        requires_human_review=has_sensitive,
        sensitive_lines=sensitive_lines,
        risk_flags=sorted(list(risk_flags)),
    )


def find_exact_reconciliation_matches(
    bank_transaction: Any,
    candidate_journal_entries: Sequence[Any],
    date_window_days: int = 3,
) -> ExactMatchResult:
    """Perform deterministic exact matching between bank tx and candidate entries.

    Matching Rules for Exact Match (Confidence = 1.00):
    1. Exact Amount Match: abs(bank_amount) == journal_entry_amount (diff < 0.01).
    2. Date Proximity: abs((tx_date - entry_date).days) <= date_window_days (default 3).
    3. Vendor / Description Match: Token overlap match for vendor/description strings.

    Args:
        bank_transaction: Dict or object with amount, transaction_date, description.
        candidate_journal_entries: Sequence of candidate journal entry dicts/objects.
        date_window_days: Max allowed date diff in days for exact match (default 3).

    Returns:
        ExactMatchResult with high-confidence match details.
    """

    def parse_date(d: Any) -> date | None:
        if isinstance(d, date):
            return d
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, str):
            try:
                return datetime.strptime(d[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    if isinstance(bank_transaction, dict):
        bank_amount = abs(float(bank_transaction.get("amount", 0.0)))
        tx_date = parse_date(bank_transaction.get("transaction_date"))
        tx_desc = bank_transaction.get("description", "")
    else:
        bank_amount = abs(float(getattr(bank_transaction, "amount", 0.0)))
        tx_date = parse_date(getattr(bank_transaction, "transaction_date", None))
        tx_desc = getattr(bank_transaction, "description", "")

    evaluated: list[dict[str, Any]] = []
    exact_matches: list[dict[str, Any]] = []

    for entry in candidate_journal_entries or []:
        if isinstance(entry, dict):
            entry_id = str(entry.get("id", ""))
            entry_date = parse_date(entry.get("entry_date"))
            entry_desc = entry.get("description", "")
            debit = float(entry.get("total_debit", 0.0))
            credit = float(entry.get("total_credit", 0.0))
            entry_amt = max(debit, credit)
        else:
            entry_id = str(getattr(entry, "id", ""))
            entry_date = parse_date(getattr(entry, "entry_date", None))
            entry_desc = getattr(entry, "description", "")
            debit = float(getattr(entry, "total_debit", 0.0))
            credit = float(getattr(entry, "total_credit", 0.0))
            entry_amt = max(debit, credit)

        amount_diff = abs(bank_amount - entry_amt)
        amount_matched = amount_diff < 0.01

        days_diff = None
        date_matched = False
        if tx_date and entry_date:
            days_diff = abs((tx_date - entry_date).days)
            date_matched = days_diff <= date_window_days

        vendor_matched = _vendor_strings_match(tx_desc, entry_desc)

        is_exact = amount_matched and date_matched and vendor_matched

        candidate_eval = {
            "entry_id": entry_id,
            "amount_matched": amount_matched,
            "amount_diff": round(amount_diff, 2),
            "date_matched": date_matched,
            "days_diff": days_diff,
            "vendor_matched": vendor_matched,
            "is_exact_match": is_exact,
        }
        evaluated.append(candidate_eval)

        if is_exact:
            exact_matches.append(candidate_eval)

    if len(exact_matches) == 1:
        match = exact_matches[0]
        return ExactMatchResult(
            is_exact_match=True,
            confidence_score=1.00,
            matched_entry_id=match["entry_id"],
            match_details=match,
            evaluated_candidates=evaluated,
        )

    return ExactMatchResult(
        is_exact_match=False,
        confidence_score=0.00,
        matched_entry_id=None,
        match_details=None,
        evaluated_candidates=evaluated,
    )


def post_journal_entry_to_ledger(
    journal_entry: Any,
    db_session: Any | None = None,
    posted_by: str = "system",
) -> PostToLedgerResult:
    """Post a draft or approved journal entry to the general ledger deterministically.

    Guardrail Checks:
    1. Status Check: Entry status MUST NOT be already 'posted' or 'voided'/'rejected'.
    2. Double-Entry Balance Check: Must pass `validate_double_entry(lines)`.
       If unbalanced or invalid, posting MUST fail and reject!

    Actions on Success:
    - Update `status = "posted"`.
    - Set `posted_at = datetime.now(UTC)`.
    - If db_session provided: commit to database.

    Args:
        journal_entry: Dict or SQLAlchemy JournalEntry ORM model.
        db_session: Optional SQLAlchemy session for persistence.
        posted_by: Optional user/system identifier.

    Returns:
        PostToLedgerResult detailing posting success, timestamp, and errors.
    """
    errors: list[str] = []

    if isinstance(journal_entry, dict):
        entry_id = str(journal_entry.get("id", "unknown"))
        current_status = str(journal_entry.get("status", "draft"))
        lines = journal_entry.get("lines", [])
    else:
        entry_id = str(getattr(journal_entry, "id", "unknown"))
        current_status = str(getattr(journal_entry, "status", "draft"))
        lines = getattr(journal_entry, "lines", [])

    if current_status == "posted":
        errors.append(f"Journal entry [{entry_id}] is already posted to ledger.")
        return PostToLedgerResult(
            success=False,
            journal_entry_id=entry_id,
            status=current_status,
            errors=errors,
        )

    if current_status in ("voided", "rejected"):
        errors.append(f"Cannot post a {current_status} journal entry [{entry_id}].")
        return PostToLedgerResult(
            success=False,
            journal_entry_id=entry_id,
            status=current_status,
            errors=errors,
        )

    validation_res = validate_double_entry(lines)
    if not validation_res.is_valid:
        errors.append(
            f"Posting rejected for journal [{entry_id}]: "
            f"Double-entry validation failed."
        )
        errors.extend(validation_res.errors)
        return PostToLedgerResult(
            success=False,
            journal_entry_id=entry_id,
            status=current_status,
            errors=errors,
        )

    now_utc = datetime.now(UTC)
    posted_at_iso = now_utc.isoformat()

    if isinstance(journal_entry, dict):
        journal_entry["status"] = "posted"
        journal_entry["posted_at"] = posted_at_iso
    else:
        journal_entry.status = "posted"
        journal_entry.posted_at = now_utc

    if db_session:
        try:
            db_session.add(journal_entry)
            db_session.commit()
            if hasattr(db_session, "refresh"):
                db_session.refresh(journal_entry)
        except Exception as e:
            logger.error("DB Error posting journal entry %s: %s", entry_id, str(e))
            if hasattr(db_session, "rollback"):
                db_session.rollback()
            return PostToLedgerResult(
                success=False,
                journal_entry_id=entry_id,
                status=current_status,
                errors=[f"Database commit error: {str(e)}"],
            )

    logger.info(
        "Successfully posted journal entry %s to ledger at %s",
        entry_id,
        posted_at_iso,
    )

    return PostToLedgerResult(
        success=True,
        journal_entry_id=entry_id,
        status="posted",
        posted_at=posted_at_iso,
        errors=[],
    )


def save_journal_entry_safely(
    journal_data: dict[str, Any] | Any,
    db_session: Any | None = None,
    chart_of_accounts: Sequence[Any] | None = None,
    raise_on_error: bool = False,
) -> SaveJournalEntryResult:
    """Validate and safely persist a journal entry to DB with strict guardrails.

    Guardrail Rules:
    1. Double-Entry Balance Check: Runs `validate_double_entry(lines)`.
       If `is_valid` is False -> REJECT IMMEDIATELY! Do NOT save to DB.
    2. Sensitive Account Check: Runs `check_sensitive_accounts(lines, COA)`.
       If sensitive accounts are present -> auto-flag `requires_human_review = True`,
       set status to `"review_required"`, and record risk flags.

    Args:
        journal_data: Dict or Pydantic/ORM model with entry fields & lines.
        db_session: Optional SQLAlchemy Session for persistence.
        chart_of_accounts: Optional sequence of COA entries for sensitive check.
        raise_on_error: If True, raise `UnbalancedJournalEntryError` on fail.

    Returns:
        SaveJournalEntryResult with validation breakdown and save status.
    """
    if isinstance(journal_data, dict):
        lines = journal_data.get("lines", [])
        raw_status = journal_data.get("status", "draft")
        entry_date = journal_data.get("entry_date") or date.today()
        description = journal_data.get("description", "Journal Entry")
        doc_id = journal_data.get("document_id")
        ext_id = journal_data.get("extraction_id")
        agent_name = journal_data.get("agent_name", "BookkeepingAgent")
        conf_score = journal_data.get("confidence_score", 1.0)
        rationale = journal_data.get("rationale")
        existing_flags = journal_data.get("risk_flags") or []
    else:
        lines = getattr(journal_data, "lines", [])
        raw_status = getattr(journal_data, "status", "draft")
        entry_date = getattr(journal_data, "entry_date", None) or date.today()
        description = getattr(journal_data, "description", "Journal Entry")
        doc_id = getattr(journal_data, "document_id", None)
        ext_id = getattr(journal_data, "extraction_id", None)
        agent_name = getattr(journal_data, "agent_name", "BookkeepingAgent")
        conf_score = getattr(journal_data, "confidence_score", 1.0)
        rationale = getattr(journal_data, "rationale", None)
        existing_flags = getattr(journal_data, "risk_flags", []) or []

    # 1. Double-Entry Validation Guardrail
    val_res = validate_double_entry(lines)
    if not val_res.is_valid:
        logger.warning(
            "Guardrail Triggered: Rejected attempt to save unbalanced journal entry. "
            "Errors: %s",
            val_res.errors,
        )
        if raise_on_error:
            raise UnbalancedJournalEntryError(val_res)

        sens_res = SensitiveAccountCheckResult(
            has_sensitive_account=False,
            requires_human_review=False,
            sensitive_lines=[],
            risk_flags=[],
        )
        return SaveJournalEntryResult(
            success=False,
            journal_entry_id=None,
            status="rejected",
            validation_result=val_res,
            sensitive_check_result=sens_res,
            errors=[f"Guardrail Rejection: {err}" for err in val_res.errors],
        )

    # 2. Sensitive Account Check Guardrail
    sens_res = check_sensitive_accounts(lines, chart_of_accounts=chart_of_accounts)

    final_status = raw_status
    merged_risk_flags = list(set(existing_flags + sens_res.risk_flags))

    if sens_res.requires_human_review and final_status != "posted":
        final_status = "review_required"

    created_id: str | None = None

    if db_session:
        from app.models.journal import JournalEntry, JournalEntryLine

        new_entry = JournalEntry(
            document_id=doc_id,
            extraction_id=ext_id,
            entry_date=entry_date,
            description=description,
            status=final_status,
            agent_name=agent_name,
            confidence_score=conf_score,
            rationale=rationale,
            risk_flags=merged_risk_flags,
        )

        for line_idx, line in enumerate(lines, start=1):
            if isinstance(line, dict):
                ac_code = str(line.get("account_code", ""))
                ac_name = str(line.get("account_name", ""))
                deb = float(line.get("debit_amount", 0.0))
                cred = float(line.get("credit_amount", 0.0))
                l_desc = line.get("description")
            else:
                ac_code = str(getattr(line, "account_code", ""))
                ac_name = str(getattr(line, "account_name", ""))
                deb = float(getattr(line, "debit_amount", 0.0))
                cred = float(getattr(line, "credit_amount", 0.0))
                l_desc = getattr(line, "description", None)

            orm_line = JournalEntryLine(
                line_number=line_idx,
                account_code=ac_code,
                account_name=ac_name,
                debit_amount=deb,
                credit_amount=cred,
                description=l_desc,
            )
            new_entry.lines.append(orm_line)

        try:
            db_session.add(new_entry)
            db_session.commit()
            db_session.refresh(new_entry)
            created_id = str(new_entry.id)
        except Exception as e:
            logger.error("Database error saving journal entry: %s", str(e))
            db_session.rollback()
            return SaveJournalEntryResult(
                success=False,
                journal_entry_id=None,
                status="failed",
                validation_result=val_res,
                sensitive_check_result=sens_res,
                errors=[f"Database save error: {str(e)}"],
            )

    return SaveJournalEntryResult(
        success=True,
        journal_entry_id=created_id,
        status=final_status,
        validation_result=val_res,
        sensitive_check_result=sens_res,
        errors=[],
    )
