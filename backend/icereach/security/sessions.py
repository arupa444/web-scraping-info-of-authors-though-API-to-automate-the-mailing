"""Opaque session tokens (DB-stored as SHA-256) + signed CSRF tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import Session as SessionModel
from ..models import User, Workspace

_csrf_serializer = URLSafeTimedSerializer(settings.secret_key, salt="icereach-csrf")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_session(db: DbSession, user: User, workspace: Workspace) -> str:
    """Create a session row and return the raw token (only the hash is stored)."""
    raw = secrets.token_urlsafe(32)
    row = SessionModel(
        token_hash=_hash_token(raw),
        user_id=user.id,
        workspace_id=workspace.id,
        expires_at=datetime.utcnow() + timedelta(seconds=settings.session_max_age),
    )
    db.add(row)
    db.commit()
    return raw


def resolve_session(db: DbSession, raw: str) -> Optional[SessionModel]:
    if not raw:
        return None
    row = db.scalar(select(SessionModel).where(SessionModel.token_hash == _hash_token(raw)))
    if row is None:
        return None
    if row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        return None
    return row


def delete_session(db: DbSession, raw: str) -> None:
    row = db.scalar(select(SessionModel).where(SessionModel.token_hash == _hash_token(raw)))
    if row is not None:
        db.delete(row)
        db.commit()


def issue_csrf() -> str:
    return _csrf_serializer.dumps(secrets.token_urlsafe(16))


def verify_csrf(token: str, max_age: int = 60 * 60 * 24 * 14) -> bool:
    if not token:
        return False
    try:
        _csrf_serializer.loads(token, max_age=max_age)
        return True
    except BadSignature:
        return False
