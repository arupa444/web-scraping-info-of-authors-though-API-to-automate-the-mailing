"""API keys for programmatic access: 'ice_<prefix>_<secret>', only the hash stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import ApiKey


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def generate(db: DbSession, workspace_id: int, name: str, scopes: str = "") -> tuple[ApiKey, str]:
    """Create an API key. Returns (row, full_token). The full token is shown ONCE."""
    prefix = secrets.token_hex(6)          # 12 hex chars, unique lookup handle
    secret = secrets.token_urlsafe(24)     # the real secret
    row = ApiKey(
        workspace_id=workspace_id,
        prefix=prefix,
        secret_hash=_hash_secret(secret),
        name=name,
        scopes=scopes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, f"ice_{prefix}_{secret}"


def verify(db: DbSession, token: str) -> Optional[ApiKey]:
    """Resolve a presented token to its (active) ApiKey row, or None."""
    if not token or not token.startswith("ice_"):
        return None
    try:
        _, prefix, secret = token.split("_", 2)
    except ValueError:
        return None
    row = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if row is None or row.revoked_at is not None:
        return None
    if not hmac.compare_digest(row.secret_hash, _hash_secret(secret)):
        return None
    row.last_used_at = datetime.utcnow()
    db.commit()
    return row
