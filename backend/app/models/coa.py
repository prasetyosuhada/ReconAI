import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False
    )  # asset, liability, equity, revenue, expense
    normal_balance: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # debit, credit
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
