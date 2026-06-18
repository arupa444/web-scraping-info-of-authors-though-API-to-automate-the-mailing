"""API key management (workspace-scoped)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import ApiKey
from ..schemas.auth import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from ..security import apikeys
from ..security.deps import AuthContext, auth_context

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_key(body: ApiKeyCreate, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    row, token = apikeys.generate(db, ctx.workspace.id, body.name, body.scopes)
    return ApiKeyCreated(id=row.id, name=row.name, prefix=row.prefix, scopes=row.scopes, token=token)


@router.get("", response_model=list[ApiKeyOut])
def list_keys(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(
        select(ApiKey).where(ApiKey.workspace_id == ctx.workspace.id, ApiKey.revoked_at.is_(None))
    ).all()
    return [ApiKeyOut(id=r.id, name=r.name, prefix=r.prefix, scopes=r.scopes) for r in rows]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    row = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == ctx.workspace.id))
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    row.revoked_at = datetime.utcnow()
    db.commit()
