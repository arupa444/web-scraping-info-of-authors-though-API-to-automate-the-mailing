"""Monthly send quotas (per workspace)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Message, Workspace


def sent_this_month(db: Session, workspace_id: int) -> int:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    return db.scalar(
        select(func.count(Message.id)).where(
            Message.workspace_id == workspace_id, Message.status == "sent", Message.sent_at >= start
        )
    ) or 0


def remaining(db: Session, workspace: Workspace) -> Optional[int]:
    """Remaining sends this month, or None when the workspace is unlimited."""
    if not workspace.monthly_send_limit:
        return None
    return max(0, workspace.monthly_send_limit - sent_this_month(db, workspace.id))


def exceeded(db: Session, workspace: Workspace) -> bool:
    rem = remaining(db, workspace)
    return rem is not None and rem <= 0
