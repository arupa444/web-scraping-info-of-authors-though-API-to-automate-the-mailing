"""Auth dependencies: session context, role gates, CSRF, and API-key auth."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..models import ApiKey, Membership, User, Workspace
from . import apikeys, sessions


@dataclass
class AuthContext:
    user: User
    workspace: Workspace
    membership: Membership
    session_token: str


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def auth_context(request: Request, db: DbSession = Depends(get_db)) -> AuthContext:
    raw = request.cookies.get(settings.session_cookie)
    sess = sessions.resolve_session(db, raw) if raw else None
    if sess is None:
        raise _unauthorized()
    user = db.get(User, sess.user_id)
    workspace = db.get(Workspace, sess.workspace_id)
    membership = db.scalar(
        select(Membership).where(Membership.user_id == sess.user_id, Membership.workspace_id == sess.workspace_id)
    )
    if not (user and user.is_active and workspace and membership):
        raise _unauthorized()
    return AuthContext(user=user, workspace=workspace, membership=membership, session_token=raw)


def current_user(ctx: AuthContext = Depends(auth_context)) -> User:
    return ctx.user


def current_workspace(ctx: AuthContext = Depends(auth_context)) -> Workspace:
    return ctx.workspace


def require_role(*roles: str):
    def _dep(ctx: AuthContext = Depends(auth_context)) -> AuthContext:
        if ctx.membership.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return ctx
    return _dep


def api_key_auth(request: Request, db: DbSession = Depends(get_db)) -> Workspace:
    """Resolve an `Authorization: Bearer ice_..._...` token to its workspace."""
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    key: ApiKey | None = apikeys.verify(db, token)
    if key is None:
        raise _unauthorized()
    ws = db.get(Workspace, key.workspace_id)
    if ws is None:
        raise _unauthorized()
    return ws
