"""Deterministic Accounting Engine for ReconAI.

Provides rule-based validation logic for double-entry bookkeeping, trial balance,
and ledger posting guardrails.
"""

import logging
from collections.abc import Sequence
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


def _to_decimal(val: Any) -> Decimal:
    """Helper to convert float/int/str/Decimal safely to Decimal (2 decimals)."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
