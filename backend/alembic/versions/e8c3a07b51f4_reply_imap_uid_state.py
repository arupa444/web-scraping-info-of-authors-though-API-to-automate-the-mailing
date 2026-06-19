"""reply tracking IMAP incremental state (last_uid + uidvalidity)

Revision ID: e8c3a07b51f4
Revises: d4a1f6b8c920
Create Date: 2026-06-19 19:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8c3a07b51f4'
down_revision: Union[str, None] = 'd4a1f6b8c920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reply_last_uid', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('reply_uidvalidity', sa.String(length=64), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.drop_column('reply_uidvalidity')
        batch_op.drop_column('reply_last_uid')
