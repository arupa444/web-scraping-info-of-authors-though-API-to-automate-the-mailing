"""Segments: CRUD + audience preview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Segment
from ..schemas.sending import PreviewOut, SegmentIn, SegmentOut
from ..security.deps import AuthContext, auth_context
from ..services.segments import preview as preview_segment

router = APIRouter(prefix="/api/segments", tags=["segments"])


def _out(s: Segment) -> SegmentOut:
    return SegmentOut(id=s.id, name=s.name, rules=s.rules)


def _owned(db: DbSession, ctx: AuthContext, segment_id: int) -> Segment:
    s = db.scalar(select(Segment).where(Segment.id == segment_id, Segment.workspace_id == ctx.workspace.id))
    if s is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    return s


@router.post("", response_model=SegmentOut, status_code=status.HTTP_201_CREATED)
def create_segment(body: SegmentIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    s = Segment(workspace_id=ctx.workspace.id, name=body.name, rules=body.rules)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(s)


@router.get("", response_model=list[SegmentOut])
def list_segments(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Segment).where(Segment.workspace_id == ctx.workspace.id)).all()
    return [_out(s) for s in rows]


@router.get("/{segment_id}/preview", response_model=PreviewOut)
def preview(segment_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    s = _owned(db, ctx, segment_id)
    try:
        result = preview_segment(db, ctx.workspace.id, s.rules)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return PreviewOut(count=result["count"], sample=result["sample"])


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(segment_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    db.delete(_owned(db, ctx, segment_id))
    db.commit()
