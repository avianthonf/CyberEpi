"""add control layer

Revision ID: 6c6c6c6c6c6c
Revises: 5c5c5c5c5c5c
Create Date: 2026-03-10 13:45:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = '6c6c6c6c6c6c'
down_revision = '5c5c5c5c5c5c'
branch_labels = None
depends_on = None

def upgrade():
    # control_weights table
    op.create_table(
        'control_weights',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('region_id', sa.String(length=50), nullable=False, unique=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('C1', sa.Float(), nullable=False),
        sa.Column('C2', sa.Float(), nullable=False),
        sa.Column('C3', sa.Float(), nullable=False),
        sa.Column('C4', sa.Float(), nullable=False),
        sa.Column('W_u1', sa.Float(), nullable=False),
        sa.Column('W_u2', sa.Float(), nullable=False),
        sa.Column('W_u3', sa.Float(), nullable=False),
        sa.Column('ethical_framework', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True)
    )
    
    # control_recommendations table
    op.create_table(
        'control_recommendations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('region_id', sa.String(length=50), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('weights_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('u1_recommended', sa.Float(), nullable=False),
        sa.Column('u2_recommended', sa.Float(), nullable=False),
        sa.Column('u3_recommended', sa.Float(), nullable=False),
        sa.Column('Rt_current', sa.Float(), nullable=False),
        sa.Column('Rt_predicted_30d', sa.Float(), nullable=False),
        sa.Column('cost_J', sa.Float(), nullable=False),
        sa.Column('converged', sa.Integer(), nullable=False),
        sa.Column('trajectory', sa.JSON(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True)
    )

def downgrade():
    op.drop_table('control_recommendations')
    op.drop_table('control_weights')
