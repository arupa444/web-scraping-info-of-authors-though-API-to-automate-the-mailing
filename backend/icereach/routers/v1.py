"""Public REST API (v1) — authenticated by API key (Authorization: Bearer ice_...).

Outside /api/ and Bearer-authed, so the session/CSRF machinery does not apply.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact, Message, SendingDomain, Workspace
from ..schemas.contact import ContactOut
from ..schemas.growth import V1ContactIn, V1EmailIn
from ..security.deps import api_key_auth
from ..services.esp import get_provider
from ..services.merge import html_to_text, render
from ..services.tracking import encode_token, rewrite_html
from ..config import settings

router = APIRouter(prefix="/v1", tags=["public-api"])


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(body: V1ContactIn, ws: Workspace = Depends(api_key_auth), db: DbSession = Depends(get_db)):
    email = body.email.lower()
    existing = db.scalar(select(Contact).where(Contact.workspace_id == ws.id, Contact.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contact already exists")
    c = Contact(workspace_id=ws.id, email=email, name=body.name, attributes=body.attributes, source="api")
    db.add(c)
    db.commit()
    db.refresh(c)
    return ContactOut(id=c.id, email=c.email, name=c.name, attributes=c.attributes or {}, status=c.status)


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(ws: Workspace = Depends(api_key_auth), db: DbSession = Depends(get_db), limit: int = 100):
    rows = db.scalars(
        select(Contact).where(Contact.workspace_id == ws.id).order_by(Contact.id).limit(min(limit, 500))
    ).all()
    return [ContactOut(id=c.id, email=c.email, name=c.name, attributes=c.attributes or {}, status=c.status) for c in rows]


@router.post("/emails")
def send_transactional(body: V1EmailIn, ws: Workspace = Depends(api_key_auth), db: DbSession = Depends(get_db)):
    domain = db.scalar(select(SendingDomain).where(SendingDomain.id == body.sending_domain_id, SendingDomain.workspace_id == ws.id))
    if domain is None:
        raise HTTPException(status_code=404, detail="Sending domain not found")
    if domain.provider == "smtp" and not domain.smtp_host:
        raise HTTPException(status_code=400, detail="Sending domain has no transport configured")

    to_email = body.to.lower()
    contact = db.scalar(select(Contact).where(Contact.workspace_id == ws.id, Contact.email == to_email))
    if contact is None:
        contact = Contact(workspace_id=ws.id, email=to_email, status="subscribed", source="transactional")
        db.add(contact)
        db.flush()

    msg_row = Message(workspace_id=ws.id, contact_id=contact.id, status="queued")
    db.add(msg_row)
    db.flush()

    row = {"name": contact.name or "", "email": contact.email, **(contact.attributes or {})}
    html = rewrite_html(render(body.html, row), msg_row.id)
    text = render(body.text or html_to_text(body.html), row)
    from_email = body.from_email or f"noreply@{domain.domain}"
    unsub = f"{settings.base_url}/u/{encode_token(msg_row.id)}"

    provider = get_provider(domain)
    try:
        provider.open()
        msg_row.message_id = provider.send(from_name=body.from_name, from_email=from_email, to_email=to_email,
                                           subject=render(body.subject, row), html=html, text=text, list_unsub_url=unsub)
        msg_row.status = "sent"
        msg_row.sent_at = datetime.utcnow()
    except Exception as exc:  # noqa: BLE001
        msg_row.status = "failed"
        msg_row.error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}")
    finally:
        provider.close()
    db.commit()
    return {"id": msg_row.id, "message_id": msg_row.message_id, "status": msg_row.status}
