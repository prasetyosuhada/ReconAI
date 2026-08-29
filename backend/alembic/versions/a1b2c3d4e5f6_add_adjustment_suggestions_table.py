"""add_adjustment_suggestions_table

Revision ID: a1b2c3d4e5f6
Revises: 20fac4e950fa
Create Date: 2026-08-18 10:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "20fac4e950fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adjustment_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "bank_transaction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(5, 4),
            nullable=False,
            server_default="0.0000",
        ),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_balanced", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "uses_sensitive_account",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "risk_flags",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "suggested_lines",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "agent_name",
            sa.String(100),
            nullable=False,
            server_default="bookkeeping_agent",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_adjustment_suggestions_bank_transaction_id",
        "adjustment_suggestions",
        ["bank_transaction_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_adjustment_suggestions_bank_transaction_id",
        table_name="adjustment_suggestions",
    )
    op.drop_table("adjustment_suggestions")
