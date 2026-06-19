"""Inbound ESP event webhooks (delivered / bounce / complaint).

Lives outside /api/ so the CSRF middleware does not guard it. Events are mapped
back to a Message by the provider message id (tenant-safe) or, failing that, by
the recipient's most recent message. Complaints and hard bounces suppress the
address; delivered/complaint events make those analytics metrics real (P4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact, Event, Message, Suppression

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# provider event name -> normalized type
_RESEND = {"email.delivered": "delivered", "email.bounced": "bounce", "email.complained": "complaint"}
_SENDGRID = {"delivered": "delivered", "bounce": "bounce", "dropped": "bounce", "spamreport": "complaint"}


@router.post("/inbound/{token}")
async def inbound_reply(token: str, request: Request, db: DbSession = Depends(get_db)):
    """Record a reply forwarded here by ANY inbound source (Cloudflare Email
    Routing worker, SendGrid Inbound Parse, a mail filter, etc.) — the free
    alternative to polling a paid POP/IMAP mailbox.

    Accepts the reply as raw RFC822 (default), multipart form (``email``/``raw``/
    ``headers`` field), or JSON (``raw``/``email`` or direct ``in_reply_to`` /
    ``references``). The workspace is taken from the signed token in the URL.
    """
    import json as _json

    from ..services.replies import (
        extract_reply_targets,
        record_reply,
        targets_from_headers,
        workspace_from_inbound_token,
    )

    try:
        workspace_id = workspace_from_inbound_token(token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown inbound token")

    ctype = request.headers.get("content-type", "").lower()
    raw = await request.body()
    targets: list[str] = []

    if "application/json" in ctype:
        try:
            data = _json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            data = {}
        if isinstance(data, dict):
            targets += targets_from_headers(
                str(data.get("in_reply_to") or data.get("In-Reply-To") or ""),
                str(data.get("references") or data.get("References") or ""),
            )
            blob = data.get("raw") or data.get("email") or data.get("message")
            if blob:
                targets += extract_reply_targets(blob.encode() if isinstance(blob, str) else blob)
    elif "multipart/form-data" in ctype or "x-www-form-urlencoded" in ctype:
        form = await request.form()
        for key in ("email", "raw", "message", "headers"):
            val = form.get(key)
            if val:
                targets += extract_reply_targets(val if isinstance(val, (bytes, bytearray)) else str(val).encode())
    else:
        targets += extract_reply_targets(raw)  # raw RFC822 (Cloudflare Email Worker)

    targets = list(dict.fromkeys(t for t in targets if t))
    recorded = record_reply(db, workspace_id, targets)
    return {"recorded": bool(recorded)}


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
                # SendGrid's sg_message_id is "<X-Message-Id>.<recv-time>.<...>"; we store
                # the base X-Message-Id at send time, so key on the leading segment.
                sg_id = (ev.get("sg_message_id", "") or "").split(".")[0]
                out.append((etype, ev.get("email", ""), sg_id))
    return out


def _find_message(db: DbSession, message_id: str) -> Message | None:
    # Resolve ONLY by the provider message id (tenant-safe). The previous
    # email fallback was workspace-unscoped, letting an unauthenticated webhook
    # suppress/bounce an address in any tenant that mails it — removed.
    if not message_id:
        return None
    return db.scalar(select(Message).where(Message.message_id == message_id))


def _apply(db: DbSession, etype: str, email: str, message_id: str) -> bool:
    msg = _find_message(db, message_id)
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
    from ..config import settings
    if settings.webhook_secret and request.query_params.get("secret") != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = None
    applied = 0
    for etype, email, message_id in _normalize(provider, body):
        if _apply(db, etype, email, message_id):
            applied += 1
    return {"received": applied}
