"""Automation journey engine: enroll contacts, advance runs through ordered steps.

Step types:
- send      : email the contact via the Phase-1 SMTP/DKIM/tracking pipeline
- wait      : pause the run until now + delay, then continue
- condition : evaluate the segment-rule DSL; continue if matched, else exit the run

A run advances step-by-step per tick, looping until it hits a `wait` (future
next_run_at) or a terminal state. The queue handler `advance_automations`
processes all due runs and should be enqueued on a schedule.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import (
    Automation,
    AutomationRun,
    AutomationStep,
    Contact,
    Message,
    SendingDomain,
    Suppression,
    Template,
)
from .esp import get_provider
from .merge import html_to_text, render
from .queue import register
from .segments import build_filter
from .tracking import encode_token, rewrite_html, unsubscribe_footer_html, unsubscribe_footer_text


def _steps(db: DbSession, automation_id: int) -> list[AutomationStep]:
    return list(db.scalars(
        select(AutomationStep).where(AutomationStep.automation_id == automation_id).order_by(AutomationStep.position)
    ).all())


def enroll(db: DbSession, automation: Automation, contact: Contact) -> Optional[AutomationRun]:
    """Enroll a contact into an active automation (no-op if already active in it)."""
    if automation.status != "active":
        return None
    existing = db.scalar(
        select(AutomationRun).where(
            AutomationRun.automation_id == automation.id,
            AutomationRun.contact_id == contact.id,
            AutomationRun.status == "active",
        )
    )
    if existing is not None:
        return None
    run = AutomationRun(
        workspace_id=automation.workspace_id, automation_id=automation.id,
        contact_id=contact.id, position=0, status="active", next_run_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def enroll_for_list(db: DbSession, workspace_id: int, list_id: int, contact_ids: list[int]) -> int:
    """Enroll contacts into active list_subscribe automations for the given list."""
    autos = db.scalars(
        select(Automation).where(
            Automation.workspace_id == workspace_id,
            Automation.status == "active",
            Automation.trigger_type == "list_subscribe",
            Automation.trigger_list_id == list_id,
        )
    ).all()
    count = 0
    for auto in autos:
        for cid in contact_ids:
            contact = db.get(Contact, cid)
            if contact is not None and enroll(db, auto, contact) is not None:
                count += 1
    return count


def _matches(db: DbSession, run: AutomationRun, rules: dict) -> bool:
    if not rules:
        return True
    expr = build_filter(rules)  # raises ValueError on a bad rule -> run fails
    hit = db.scalar(
        select(Contact).where(Contact.id == run.contact_id, Contact.workspace_id == run.workspace_id, expr)
    )
    return hit is not None


def _send_step(db: DbSession, run: AutomationRun, automation: Automation, step: AutomationStep) -> None:
    contact = db.get(Contact, run.contact_id)
    if contact is None:
        return
    # Respect suppression + unsubscribed contacts.
    if contact.status != "subscribed":
        return
    if db.scalar(select(Suppression).where(Suppression.workspace_id == automation.workspace_id, Suppression.email == contact.email)):
        return

    domain = db.get(SendingDomain, automation.sending_domain_id) if automation.sending_domain_id else None
    if domain is None or not domain.smtp_host:
        raise ValueError("Automation has no configured sending domain / SMTP relay")

    cfg = step.config or {}
    if cfg.get("template_id"):
        # Scope to the automation's workspace — never read another tenant's template.
        tpl = db.scalar(select(Template).where(
            Template.id == cfg["template_id"], Template.workspace_id == automation.workspace_id))
        if tpl is None:
            raise ValueError("Step references a missing template")
        subject, html, text = tpl.subject, tpl.html, tpl.text
    else:
        subject = cfg.get("subject", "")
        html = cfg.get("html", "")
        text = cfg.get("text", "") or html_to_text(html)

    msg_row = Message(
        workspace_id=automation.workspace_id, automation_id=automation.id,
        contact_id=contact.id, status="queued",
    )
    db.add(msg_row)
    db.flush()

    row = {"name": contact.name or "", "email": contact.email, **(contact.attributes or {})}
    subj = render(subject, row)
    body_html = rewrite_html(render(html, row), msg_row.id)
    body_text = render(text, row)
    unsub = f"{settings.base_url}/u/{encode_token(msg_row.id)}"
    body_html += unsubscribe_footer_html(unsub)
    body_text += unsubscribe_footer_text(unsub)

    provider = get_provider(domain)
    try:
        provider.open()
        msg_row.message_id = provider.send(
            from_name=automation.from_name, from_email=automation.from_email, to_email=contact.email,
            subject=subj, html=body_html, text=body_text, list_unsub_url=unsub,
        )
        msg_row.status = "sent"
        msg_row.sent_at = datetime.utcnow()
    finally:
        provider.close()
    # NOTE: no commit here — the caller commits the sent Message together with the
    # run.position advance so the cursor can never lag behind a recorded send.


def advance_run(db: DbSession, run: AutomationRun) -> None:
    """Advance a single run through as many steps as are due this tick."""
    automation = db.get(Automation, run.automation_id)
    steps = _steps(db, run.automation_id)
    # A run is processable whether freshly active (direct call/tests) or claimed
    # by advance_due_runs (status 'running').
    try:
        while run.status in ("active", "running") and run.next_run_at <= datetime.utcnow():
            if run.position >= len(steps):
                run.status = "done"
                db.commit()
                break
            step = steps[run.position]
            if step.type == "send":
                _send_step(db, run, automation, step)
                run.position += 1
            elif step.type == "wait":
                run.position += 1
                run.next_run_at = datetime.utcnow() + timedelta(hours=_wait_hours(step.config or {}))
                run.status = "active"  # release the claim; re-picked when due
                db.commit()
                return  # paused until next_run_at
            elif step.type == "condition":
                if _matches(db, run, (step.config or {}).get("rules", {})):
                    run.position += 1
                else:
                    run.status = "exited"
            else:
                run.position += 1  # unknown step type — skip
            db.commit()

        if run.position >= len(steps) and run.status in ("active", "running"):
            run.status = "done"
        elif run.status == "running":
            run.status = "active"  # safety: never leave a run stuck 'running'
        db.commit()  # always persist the final state (done/exited/active)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(AutomationRun, run.id)
        run.status = "failed"
        run.last_error = str(exc)
        db.commit()


def _wait_hours(cfg: dict) -> float:
    """Coerce a wait step's delay to non-negative hours (bad config -> 24h)."""
    try:
        hours = cfg.get("delay_hours")
        if hours is None:
            hours = float(cfg.get("delay_days", 1)) * 24
        return max(0.0, float(hours))
    except (TypeError, ValueError):
        return 24.0


def advance_due_runs(db: DbSession, limit: int = 200) -> int:
    from sqlalchemy import update
    candidates = db.scalars(
        select(AutomationRun)
        .where(AutomationRun.status == "active", AutomationRun.next_run_at <= datetime.utcnow())
        .order_by(AutomationRun.next_run_at)
        .limit(limit)
    ).all()
    runs = []
    for cand in candidates:
        # Atomically claim (active -> running); skip if another worker won the race.
        res = db.execute(
            update(AutomationRun).where(AutomationRun.id == cand.id, AutomationRun.status == "active")
            .values(status="running")
        )
        db.commit()
        if res.rowcount == 1:
            db.refresh(cand)
            runs.append(cand)
    for run in runs:
        advance_run(db, run)
    return len(runs)


@register("advance_automations")
def advance_automations_job(db: DbSession, job, progress) -> dict:
    n = advance_due_runs(db)
    return {"advanced": n}
