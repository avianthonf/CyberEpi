"""add_filter_states_table

Revision ID: 8c84bfd0a00c
Revises: 6c6c6c6c6c6c
Create Date: 2026-08-21 09:17:38.192689
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8c84bfd0a00c'
down_revision: str | None = '6c6c6c6c6c6c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'filter_states',
        sa.Column('region_id', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('filter_type', sa.String(length=20), nullable=False),
        sa.Column('state_vector', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('covariance_matrix', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('cusum_score', sa.Float(), nullable=False),
        sa.Column('fail_count', sa.Integer(), nullable=False),
        sa.Column('last_observation', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('last_innovation', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('last_chi2', sa.Float(), nullable=True),
        sa.Column('observation_history', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('region_id'),
    )


def downgrade() -> None:
    op.drop_table('filter_states')
