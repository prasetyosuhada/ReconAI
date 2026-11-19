"""Validate the editable Bookkeeping fields against the persisted chart of accounts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.models.coa import ChartOfAccount
from app.models.journal import JournalEntry, JournalEntryLine


class ReviewedLine(BaseModel):
    account_code: str
    debit_amount: Decimal = Decimal(0)
    credit_amount: Decimal = Decimal(0)
    description: str | None = None


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class EditedLine(ReviewedLine):
    model_config = ConfigDict(extra="forbid")

    account_code: str = Field(min_length=1, max_length=50)
    account_name: str | None = None
    debit_amount: Money = Decimal(0)
    credit_amount: Money = Decimal(0)


class JournalEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[EditedLine] | None = Field(
        default=None,
        validation_alias=AliasChoices("lines", "journal_lines"),
        min_length=2,
    )
    entry_date: date | None = None
    description: str | None = Field(default=None, min_length=1)


def apply_journal_edits(
    db: Session, entry: JournalEntry, payload: dict[str, Any]
) -> bool:
    """Stage header and line edits. Return whether the reviewer supplied new lines."""
    if not payload or any(value is None for value in payload.values()):
        raise ValueError(
            "Provide journal lines, an entry date or a description to edit."
        )
    try:
        edits = JournalEdits.model_validate(payload)
    except ValidationError as exc:
        error = exc.errors(include_input=False)[0]
        field = ".".join(str(part) for part in error["loc"])
        raise ValueError(f"Invalid journal edit at {field}: {error['msg']}.") from exc

    if edits.entry_date is not None:
        if payload["entry_date"] != edits.entry_date.isoformat():
            raise ValueError("Use YYYY-MM-DD for the journal entry date.")
        entry.entry_date = edits.entry_date
    if edits.description is not None:
        if not edits.description.strip():
            raise ValueError("The journal description cannot be blank.")
        entry.description = edits.description
    if edits.lines is None:
        return False

    codes = {line.account_code for line in edits.lines}
    accounts = db.query(ChartOfAccount).filter(
        ChartOfAccount.is_active.is_(True),
        ChartOfAccount.account_code.in_(codes),
    )
    by_code = {account.account_code: account for account in accounts}
    replacements = []
    for number, line in enumerate(edits.lines, start=1):
        account = by_code.get(line.account_code)
        if account is None:
            raise ValueError(f"Line {number} requires an existing active account.")
        replacements.append(
            JournalEntryLine(
                line_number=number,
                account=account,
                description=line.description,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
            )
        )
    # Release the previous (journal, line number) keys inside this transaction.
    entry.lines.clear()
    db.flush()
    entry.lines.extend(replacements)
    return True
