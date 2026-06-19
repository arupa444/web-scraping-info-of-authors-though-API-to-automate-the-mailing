"""Automations: CRUD, activate/pause, enroll, runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Automation, AutomationRun, AutomationStep, Contact, Segment
from ..schemas.automation import AutomationIn, AutomationOut, EnrollIn, RunOut, StepOut
from ..security.deps import AuthContext, auth_context
from ..services import automation as engine
from ..services.segments import evaluate as evaluate_segment

router = APIRouter(prefix="/api/automations", tags=["automations"])


def _steps_out(db: DbSession, automation_id: int) -> list[StepOut]:
    rows = db.scalars(
        select(AutomationStep).where(AutomationStep.automation_id == automation_id).order_by(AutomationStep.position)
    ).all()
    return [StepOut(id=s.id, position=s.position, type=s.type, config=s.config) for s in rows]


def _out(db: DbSession, a: Automation) -> AutomationOut:
    return AutomationOut(
        id=a.id, name=a.name, status=a.status, trigger_type=a.trigger_type,
        trigger_list_id=a.trigger_list_id, sending_domain_id=a.sending_domain_id,
        from_name=a.from_name, from_email=a.from_email, steps=_steps_out(db, a.id),
    )


def _owned(db: DbSession, ctx: AuthContext, automation_id: int) -> Automation:
    a = db.scalar(select(Automation).where(Automation.id == automation_id, Automation.workspace_id == ctx.workspace.id))
    if a is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return a


def _replace_steps(db: DbSession, automation: Automation, steps) -> None:
    for old in db.scalars(select(AutomationStep).where(AutomationStep.automation_id == automation.id)).all():
        db.delete(old)
    for i, s in enumerate(steps):
        db.add(AutomationStep(automation_id=automation.id, position=i, type=s.type, config=s.config))


def _validate_refs(db: DbSession, ctx: AuthContext, body: AutomationIn) -> None:
    """Reject references to another tenant's sending domain / trigger list."""
    from ..models import ContactList, SendingDomain
    if body.sending_domain_id is not None and db.scalar(
        select(SendingDomain).where(SendingDomain.id == body.sending_domain_id, SendingDomain.workspace_id == ctx.workspace.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Sending domain not found")
    if body.trigger_list_id is not None and db.scalar(
        select(ContactList).where(ContactList.id == body.trigger_list_id, ContactList.workspace_id == ctx.workspace.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Trigger list not found")


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
def create_automation(body: AutomationIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    _validate_refs(db, ctx, body)
    a = Automation(
        workspace_id=ctx.workspace.id, name=body.name, status="draft",
        trigger_type=body.trigger_type, trigger_list_id=body.trigger_list_id,
        sending_domain_id=body.sending_domain_id, from_name=body.from_name, from_email=body.from_email,
    )
    db.add(a)
    db.flush()
    _replace_steps(db, a, body.steps)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.get("", response_model=list[AutomationOut])
def list_automations(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Automation).where(Automation.workspace_id == ctx.workspace.id).order_by(Automation.id.desc())).all()
    return [_out(db, a) for a in rows]


@router.get("/{automation_id}", response_model=AutomationOut)
def get_automation(automation_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    return _out(db, _owned(db, ctx, automation_id))


@router.put("/{automation_id}", response_model=AutomationOut)
def update_automation(automation_id: int, body: AutomationIn, ctx: AuthContext = Depends(auth_context),
                      db: DbSession = Depends(get_db)):
    a = _owned(db, ctx, automation_id)
    _validate_refs(db, ctx, body)
    a.name = body.name
    a.trigger_type = body.trigger_type
    a.trigger_list_id = body.trigger_list_id
    a.sending_domain_id = body.sending_domain_id
    a.from_name = body.from_name
    a.from_email = body.from_email
    _replace_steps(db, a, body.steps)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(automation_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    db.delete(_owned(db, ctx, automation_id))
    db.commit()


@router.post("/{automation_id}/activate", response_model=AutomationOut)
def activate(automation_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    a = _owned(db, ctx, automation_id)
    if not _steps_out(db, a.id):
        raise HTTPException(status_code=400, detail="Automation has no steps")
    a.status = "active"
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.post("/{automation_id}/pause", response_model=AutomationOut)
def pause(automation_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    a = _owned(db, ctx, automation_id)
    a.status = "paused"
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.post("/{automation_id}/enroll")
def enroll(automation_id: int, body: EnrollIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    a = _owned(db, ctx, automation_id)
    if a.status != "active":
        raise HTTPException(status_code=400, detail="Activate the automation before enrolling")
    contacts: list[Contact] = []
    if body.segment_id is not None:
        seg = db.scalar(select(Segment).where(Segment.id == body.segment_id, Segment.workspace_id == ctx.workspace.id))
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found")
        contacts = evaluate_segment(db, ctx.workspace.id, seg.rules)
    if body.contact_ids:
        contacts += db.scalars(
            select(Contact).where(Contact.id.in_(body.contact_ids), Contact.workspace_id == ctx.workspace.id)
        ).all()
    enrolled = sum(1 for c in contacts if engine.enroll(db, a, c) is not None)
    return {"enrolled": enrolled}


@router.get("/{automation_id}/runs", response_model=list[RunOut])
def runs(automation_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db), limit: int = 100):
    _owned(db, ctx, automation_id)
    rows = db.scalars(
        select(AutomationRun).where(AutomationRun.automation_id == automation_id).order_by(AutomationRun.id.desc()).limit(min(limit, 500))
    ).all()
    return [RunOut(id=r.id, contact_id=r.contact_id, position=r.position, status=r.status,
                   next_run_at=r.next_run_at, last_error=r.last_error) for r in rows]
