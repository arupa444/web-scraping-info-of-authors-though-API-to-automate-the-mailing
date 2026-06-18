"""Background job status (workspace-scoped)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Job
from ..schemas.contact import JobOut
from ..security.deps import AuthContext, auth_context

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _out(j: Job) -> JobOut:
    return JobOut(id=j.id, type=j.type, status=j.status, progress=j.progress,
                  message=j.message, result=j.result, error=j.error)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    j = db.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == ctx.workspace.id))
    if j is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _out(j)


@router.get("", response_model=list[JobOut])
def list_jobs(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db), limit: int = 50):
    rows = db.scalars(
        select(Job).where(Job.workspace_id == ctx.workspace.id).order_by(Job.id.desc()).limit(min(limit, 200))
    ).all()
    return [_out(j) for j in rows]
