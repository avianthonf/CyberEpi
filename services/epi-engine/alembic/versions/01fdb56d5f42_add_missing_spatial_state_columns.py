"""add_missing_spatial_state_columns

Revision ID: 01fdb56d5f42
Revises: a1b2c3d4e5f6
Create Date: 2026-10-18 02:10:59.490000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "01fdb56d5f42"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add missing columns to spatial_states table
    # H (Hospitalized), D (Deaths), N (Total population), Rt (Reproduction number)

    # H: Hospitalized - nullable, follows E pattern
    op.add_column("spatial_states", sa.Column("H", sa.Float(), nullable=True))

    # D: Deaths - nullable
    op.add_column("spatial_states", sa.Column("D", sa.Float(), nullable=True))

    # N: Total population - nullable=False with default based on model
    # Existing rows get a sensible default: sum of compartments where available
    # For historical rows without values, we backfill with S+E+I+R as proxy
    op.add_column("spatial_states", sa.Column("N", sa.Float(), nullable=True))

    # Backfill N with computed value from existing compartments
    op.execute("""
        UPDATE spatial_states
        SET "N" = COALESCE("S", 0) + COALESCE("E", 0) + COALESCE("I", 0) + COALESCE("R", 0)
        WHERE "N" IS NULL
    """)

    # Now make N non-nullable to match model
    op.alter_column("spatial_states", "N", nullable=False)

    # Rt: Reproduction number - nullable (computed value, may not always exist)
    op.add_column("spatial_states", sa.Column("Rt", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("spatial_states", "Rt")
    op.drop_column("spatial_states", "N")
    op.drop_column("spatial_states", "D")
    op.drop_column("spatial_states", "H")
