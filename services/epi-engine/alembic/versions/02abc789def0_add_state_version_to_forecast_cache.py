"""add_state_version_to_forecast_cache

Revision ID: 02abc789def0
Revises: 01fdb56d5f42
Create Date: 2026-10-30 13:18:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02abc789def0"
down_revision: str | None = "01fdb56d5f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add state_version column to forecast_cache table
    # This enables cache invalidation when filter state updates from new observations
    op.add_column("forecast_cache", sa.Column("state_version", sa.String(64), nullable=True))

    # Backfill existing rows with "bootstrap" (forecasts computed without filtered state)
    op.execute("""
        UPDATE forecast_cache
        SET state_version = 'bootstrap'
        WHERE state_version IS NULL
    """)

    # Make non-nullable after backfill
    op.alter_column("forecast_cache", "state_version", nullable=False)


def downgrade() -> None:
    op.drop_column("forecast_cache", "state_version")
