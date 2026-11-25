"""add_fl_rounds_table

Revision ID: 2a3f4b5c6d7e
Revises: 197bc198e56f
Create Date: 2026-10-18 01:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2a3f4b5c6d7e"
down_revision: str | None = "197bc198e56f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fl_rounds",
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("num_clients", sa.Integer(), nullable=False),
        sa.Column("model_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("aggregation_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("round_id"),
    )
    op.create_index("ix_fl_rounds_completed_at", "fl_rounds", ["completed_at"])


def downgrade() -> None:
    op.drop_index("ix_fl_rounds_completed_at", table_name="fl_rounds")
    op.drop_table("fl_rounds")
