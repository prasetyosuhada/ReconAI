import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("idx_audit_events_source", "source_type", "source_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # document_uploaded, extraction_completed, journal_entry_suggested, etc.
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # document, journal_entry, bank_transaction, review_item, etc.
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="system"
    )  # agent, human, system
    actor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    input_snapshot: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    output_snapshot: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    human_action: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # approved, edited, rejected

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
