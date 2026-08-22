"""add_surveillance_observations_table

Revision ID: a1b2c3d4e5f6
Revises: 8c84bfd0a00c
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '8c84bfd0a00c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'surveillance_observations',
        sa.Column('region_id', sa.String(length=50), nullable=False),
        sa.Column('week_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('admissions', sa.Float(), nullable=True),
        sa.Column('ili_fraction', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('region_id', 'week_end'),
    )
    op.create_index(
        'ix_surveillance_observations_week_end',
        'surveillance_observations', ['week_end'],
    )


def downgrade() -> None:
    op.drop_index('ix_surveillance_observations_week_end',
                  table_name='surveillance_observations')
    op.drop_table('surveillance_observations')
