"""SQLAlchemy model for AI-generated bookkeeping adjustment suggestions.

Created during Run Recon Engine for transactions classified as Bank Only (unmatched).
Persisted to DB so the frontend can read instantly without re-invoking the LLM.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class AdjustmentSuggestion(Base):
    """Stores BookkeepingAgent output for an unmatched BankTransaction.

    One-to-one with BankTransaction (UNIQUE constraint on bank_transaction_id).
    Upserted during Run Recon Engine and read by the Bank Only transaction view.
    """

    __tablename__ = "adjustment_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # BookkeepingAgent output fields
    confidence_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_balanced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uses_sensitive_account: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    risk_flags: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # list of {account_code, account_name, description, debit_amount, credit_amount}
    suggested_lines: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    agent_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="bookkeeping_agent"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship back to BankTransaction
    bank_transaction: Mapped["BankTransaction"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "BankTransaction", back_populates="adjustment_suggestion"
    )
