"""Add population intelligence tables

Revision ID: 5c5c5c5c5c5c
Revises: 3456789abcde
Create Date: 2026-03-10 13:20:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '5c5c5c5c5c5c'
down_revision = '658bf6edf6c7'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Mobility Matrix
    op.create_table(
        'mobility_matrix',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('region_id', sa.String(50), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('from_patch', sa.String(20), nullable=False),
        sa.Column('to_patch', sa.String(20), nullable=False),
        sa.Column('fraction', sa.Float(), nullable=False),
        sa.CheckConstraint('fraction >= 0 AND fraction <= 1', name='fraction_range_check')
    )
    op.create_index('ix_mobility_region', 'mobility_matrix', ['region_id'])

    # 2. Spatial States per Patch (Hypertable)
    op.create_table(
        'spatial_states',
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('region_id', sa.String(50), nullable=False),
        sa.Column('patch_id', sa.String(20), nullable=False),
        sa.Column('S', sa.BigInteger()),
        sa.Column('E', sa.BigInteger()),
        sa.Column('I', sa.BigInteger()),
        sa.Column('R', sa.BigInteger()),
        sa.Column('I_variance', sa.Float()),
        sa.Column('hotspot_prob', sa.Float()),
        sa.PrimaryKeyConstraint('time', 'patch_id')
    )
    # Convert to hypertable (requires timescale extension)
    op.execute("SELECT create_hypertable('spatial_states', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)")
    op.create_index('ix_spatial_states_lookup', 'spatial_states', ['region_id', 'patch_id', sa.text('time DESC')])

    # 3. Rt Estimates (Hypertable)
    op.create_table(
        'rt_estimates',
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('region_id', sa.String(50), nullable=False),
        sa.Column('patch_id', sa.String(20)), # NULL for region-wide
        sa.Column('Rt_mean', sa.Float(), nullable=False),
        sa.Column('Rt_lower', sa.Float(), nullable=False),
        sa.Column('Rt_upper', sa.Float(), nullable=False),
        sa.Column('window_days', sa.SmallInteger(), server_default='7'),
        sa.PrimaryKeyConstraint('time', 'region_id') # Note: simplified PK for hypertable
    )
    op.execute("SELECT create_hypertable('rt_estimates', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE)")
    op.create_index('ix_rt_lookup', 'rt_estimates', ['region_id', sa.text('time DESC')])

def downgrade():
    op.drop_table('rt_estimates')
    op.drop_table('spatial_states')
    op.drop_table('mobility_matrix')
