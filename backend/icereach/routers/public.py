"""Public, unauthenticated endpoints: open pixel, click redirect, unsubscribe.

These live outside /api/ so the CSRF middleware does not guard them — mailbox
providers issue one-click unsubscribe POSTs with no cookies.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact, Event, ListMembership, Message, Suppression
from ..services.tracking import decode_token, is_bot

router = APIRouter(tags=["public"])

# 1x1 transparent PNG
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _record_event(db: DbSession, message_id: int, etype: str, request: Request, url: str = "") -> Message | None:
    msg = db.get(Message, message_id)
    if msg is None:
        return None
    ua = request.headers.get("user-agent", "")
    if etype in ("open", "click") and is_bot(ua):
        return msg  # ignore bot/prefetch hits
    db.add(Event(workspace_id=msg.workspace_id, message_id=msg.id, type=etype, url=url or None, user_agent=ua[:500]))
    db.commit()
    return msg


@router.get("/t/o/{token}.png")
def track_open(token: str, request: Request, db: DbSession = Depends(get_db)):
    try:
        data = decode_token(token)
        _record_event(db, int(data["message_id"]), "open", request)
    except Exception:
        pass  # never break the pixel
    return Response(content=_PIXEL, media_type="image/png")


@router.get("/t/c/{token}")
def track_click(token: str, request: Request, db: DbSession = Depends(get_db)):
    try:
        data = decode_token(token)
        target = data.get("url") or "/"
        _record_event(db, int(data["message_id"]), "click", request, url=target)
        return RedirectResponse(url=target, status_code=302)
    except Exception:
        return RedirectResponse(url="/", status_code=302)


_UNSUB_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Unsubscribe</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:64px auto;padding:0 16px;text-align:center;color:#111827">
<h2 style="margin-bottom:8px">Unsubscribe</h2>
<p style="color:#6b7280;margin-top:0">You're still subscribed. Click the button below to confirm
and stop receiving these emails.</p>
<form method="post" action="/u/{token}"><button type="submit"
  style="padding:12px 22px;font-size:16px;border:0;border-radius:8px;background:#dc2626;color:#fff;cursor:pointer">
  Confirm unsubscribe</button></form>
</body></html>"""

_UNSUB_DONE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Unsubscribed</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:64px auto;padding:0 16px;text-align:center;color:#111827">
<h2>You're unsubscribed</h2>
<p style="color:#6b7280">You will no longer receive these emails. You can close this page.</p>
</body></html>"""


def _do_unsubscribe(db: DbSession, token: str) -> bool:
    try:
        data = decode_token(token)
    except Exception:
        return False
    msg = db.get(Message, int(data["message_id"]))
    if msg is None:
        return False
    contact = db.get(Contact, msg.contact_id)
    if contact is None:
        return False
    # suppress (idempotent)
    existing = db.scalar(
        select(Suppression).where(Suppression.workspace_id == msg.workspace_id, Suppression.email == contact.email)
    )
    if existing is None:
        db.add(Suppression(workspace_id=msg.workspace_id, email=contact.email, reason="unsubscribe"))
    contact.status = "unsubscribed"
    for lm in db.scalars(select(ListMembership).where(ListMembership.contact_id == contact.id)).all():
        lm.status = "unsubscribed"
    db.add(Event(workspace_id=msg.workspace_id, message_id=msg.id, type="unsubscribe"))
    db.commit()
    return True


@router.get("/u/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str):
    return HTMLResponse(_UNSUB_PAGE.format(token=token))


@router.post("/u/{token}")
def unsubscribe_confirm(token: str, db: DbSession = Depends(get_db)):
    # Only this POST mutates state — Gmail's one-click button posts here, and the
    # confirmation page's button posts here. A GET (scanner/prefetch/just opening
    # the link) never unsubscribes anyone.
    ok = _do_unsubscribe(db, token)
    return HTMLResponse(
        _UNSUB_DONE if ok else "<p>Invalid or expired unsubscribe link.</p>",
        status_code=200 if ok else 400,
    )
