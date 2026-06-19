"""campaign cached AI summary (+timestamp)

Revision ID: b7e2a9c14d05
Revises: f3d01c668f48
Create Date: 2026-06-19 17:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2a9c14d05'
down_revision: Union[str, None] = 'f3d01c668f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ai_summary_highlights', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('ai_summary_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('ai_summary_at')
        batch_op.drop_column('ai_summary_highlights')
        batch_op.drop_column('ai_summary')
