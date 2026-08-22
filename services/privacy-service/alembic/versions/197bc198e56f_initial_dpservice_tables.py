"""initial_dpservice_tables

Revision ID: 197bc198e56f
Revises:
Create Date: 2026-08-21 09:19:17.765575
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '197bc198e56f'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'dp_budgets',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('consumed', sa.Float(), nullable=False),
        sa.Column('max_budget', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reset_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )

    op.create_table(
        'dp_queries',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('mechanism', sa.String(length=50), nullable=False),
        sa.Column('epsilon', sa.Float(), nullable=False),
        sa.Column('sensitivity', sa.Float(), nullable=False),
        sa.Column('query_type', sa.String(length=100), nullable=True),
        sa.Column('noised_value', sa.Float(), nullable=True),
        sa.Column('query_metadata', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dp_queries_user_id_timestamp', 'dp_queries', ['user_id', 'timestamp'])


def downgrade() -> None:
    op.drop_index('ix_dp_queries_user_id_timestamp', table_name='dp_queries')
    op.drop_table('dp_queries')
    op.drop_table('dp_budgets')
