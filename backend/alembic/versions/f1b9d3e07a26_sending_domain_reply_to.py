"""sending_domain reply_to (Reply-To header for reply tracking)

Revision ID: f1b9d3e07a26
Revises: e8c3a07b51f4
Create Date: 2026-06-19 20:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1b9d3e07a26'
down_revision: Union[str, None] = 'e8c3a07b51f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reply_to', sa.String(length=320), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.drop_column('reply_to')
