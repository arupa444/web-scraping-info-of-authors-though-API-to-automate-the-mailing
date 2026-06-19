"""sending_domain reply mailbox (POP3/IMAP reply tracking)

Revision ID: d4a1f6b8c920
Revises: b7e2a9c14d05
Create Date: 2026-06-19 18:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a1f6b8c920'
down_revision: Union[str, None] = 'b7e2a9c14d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reply_protocol', sa.String(length=10), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('reply_host', sa.String(length=255), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('reply_port', sa.Integer(), nullable=False, server_default='995'))
        batch_op.add_column(sa.Column('reply_username', sa.String(length=320), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('reply_password', sa.Text(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('reply_seen_uids', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('sending_domains', schema=None) as batch_op:
        batch_op.drop_column('reply_seen_uids')
        batch_op.drop_column('reply_password')
        batch_op.drop_column('reply_username')
        batch_op.drop_column('reply_port')
        batch_op.drop_column('reply_host')
        batch_op.drop_column('reply_protocol')
