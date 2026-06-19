"""Inbound ESP event webhooks (delivered / bounce / complaint).

Lives outside /api/ so the CSRF middleware does not guard it. Events are mapped
back to a Message by the provider message id (tenant-safe) or, failing that, by
the recipient's most recent message. Complaints and hard bounces suppress the
address; delivered/complaint events make those analytics metrics real (P4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact, Event, Message, Suppression

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# provider event name -> normalized type
_RESEND = {"email.delivered": "delivered", "email.bounced": "bounce", "email.complained": "complaint"}
_SENDGRID = {"delivered": "delivered", "bounce": "bounce", "dropped": "bounce", "spamreport": "complaint"}


def _normalize(provider: str, body: Any) -> list[tuple[str, str, str]]:
    """Return a list of (event_type, email, message_id) tuples."""
    out: list[tuple[str, str, str]] = []
    if provider == "resend" and isinstance(body, dict):
        etype = _RESEND.get(body.get("type", ""))
        data = body.get("data") or {}
        to = data.get("to")
        email = (to[0] if isinstance(to, list) and to else to) or data.get("email") or ""
        if etype:
            out.append((etype, email, data.get("email_id", "")))
    elif provider == "sendgrid" and isinstance(body, list):
        for ev in body:
            if not isinstance(ev, dict):
                continue
            etype = _SENDGRID.get(ev.get("event", ""))
            if etype:
                out.append((etype, ev.get("email", ""), ev.get("sg_message_id", "")))
    return out


def _find_message(db: DbSession, email: str, message_id: str) -> Message | None:
    if message_id:
        msg = db.scalar(select(Message).where(Message.message_id == message_id))
        if msg is not None:
            return msg
    if email:
        return db.scalar(
            select(Message).join(Contact, Contact.id == Message.contact_id)
            .where(Contact.email == email).order_by(Message.id.desc())
        )
    return None


def _apply(db: DbSession, etype: str, email: str, message_id: str) -> bool:
    msg = _find_message(db, email, message_id)
    if msg is None:
        return False
    ws = msg.workspace_id
    if etype == "bounce":
        msg.status = "hard_bounce"
    db.add(Event(workspace_id=ws, message_id=msg.id, type=etype))
    if etype in ("bounce", "complaint"):
        contact = db.get(Contact, msg.contact_id)
        if contact is not None:
            reason = "complaint" if etype == "complaint" else "hard_bounce"
            existing = db.scalar(select(Suppression).where(Suppression.workspace_id == ws, Suppression.email == contact.email))
            if existing is None:
                db.add(Suppression(workspace_id=ws, email=contact.email, reason=reason))
    db.commit()
    return True


@router.post("/{provider}")
async def receive(provider: str, request: Request, db: DbSession = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = None
    applied = 0
    for etype, email, message_id in _normalize(provider, body):
        if _apply(db, etype, email, message_id):
            applied += 1
    return {"received": applied}
