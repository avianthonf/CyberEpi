"""add_patient_id_fk

Revision ID: 0fed6465e977
Revises: 
Create Date: 2026-08-20 09:25:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0fed6465e977'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        'fk_push_tokens_patient_id_patients',
        'push_tokens', 'patients',
        ['patient_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_push_tokens_patient_id_patients', 'push_tokens', type_='foreignkey')
