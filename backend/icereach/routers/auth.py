"""Authentication: signup, login, logout, me."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..models import Membership, User, Workspace
from ..schemas.auth import LoginIn, MeOut, SignupIn, UserOut, WorkspaceOut
from ..security import sessions
from ..security.deps import AuthContext, auth_context
from ..security.passwords import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return base


def _unique_slug(db: DbSession, name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 1
    while db.scalar(select(Workspace).where(Workspace.slug == slug)) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


def _set_auth_cookies(response: Response, session_token: str) -> None:
    response.set_cookie(
        settings.session_cookie, session_token, httponly=True, samesite="lax",
        secure=False, max_age=settings.session_max_age, path="/",
    )
    response.set_cookie(
        settings.csrf_cookie, sessions.issue_csrf(), httponly=False, samesite="lax",
        secure=False, max_age=settings.session_max_age, path="/",
    )


def _me(user: User, workspace: Workspace, role: str) -> MeOut:
    return MeOut(
        user=UserOut(id=user.id, email=user.email, name=user.name),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name, slug=workspace.slug),
        role=role,
    )


@router.post("/signup", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, response: Response, db: DbSession = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), name=body.name)
    db.add(user)
    db.flush()
    workspace = Workspace(name=body.workspace_name, slug=_unique_slug(db, body.workspace_name))
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(user)
    db.refresh(workspace)
    token = sessions.create_session(db, user, workspace)
    _set_auth_cookies(response, token)
    return _me(user, workspace, "owner")


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, db: DbSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if membership is None:
        raise HTTPException(status_code=403, detail="No workspace membership")
    workspace = db.get(Workspace, membership.workspace_id)
    token = sessions.create_session(db, user, workspace)
    _set_auth_cookies(response, token)
    return _me(user, workspace, membership.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    if ctx.session_token:
        sessions.delete_session(db, ctx.session_token)
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(settings.csrf_cookie, path="/")


@router.get("/me", response_model=MeOut)
def me(request: Request, response: Response, ctx: AuthContext = Depends(auth_context)):
    # Self-heal CSRF: if the cookie is missing or its signature is stale (server
    # restart / SECRET_KEY change), re-issue one signed with the CURRENT secret so
    # mutations don't wedge on "CSRF validation failed". If it's already valid,
    # leave it untouched (stable value for the double-submit check).
    current = request.cookies.get(settings.csrf_cookie)
    if not current or not sessions.verify_csrf(current):
        response.set_cookie(
            settings.csrf_cookie, sessions.issue_csrf(), httponly=False, samesite="lax",
            secure=False, max_age=settings.session_max_age, path="/",
        )
    return _me(ctx.user, ctx.workspace, ctx.membership.role)
