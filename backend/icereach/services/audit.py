"""Audit logging helper."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import AuditLog


def log(db: Session, workspace_id: int, action: str, target: Optional[str] = None,
        user_id: Optional[int] = None, meta: Optional[dict] = None) -> None:
    db.add(AuditLog(workspace_id=workspace_id, user_id=user_id, action=action, target=target, meta=meta or {}))
    db.commit()
