"""Signup form handling with optional double opt-in confirmation."""

from __future__ import annotations

from datetime import datetime

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import Contact, ListMembership, SendingDomain, SignupForm
from .automation import enroll_for_list
from .esp import get_provider
from .validation import is_valid_syntax

_serializer = URLSafeSerializer(settings.secret_key, salt="icereach-confirm")


def make_token(form_id: int, email: str, name: str = "") -> str:
    return _serializer.dumps({"f": form_id, "e": email, "n": name})


def read_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token)
    except BadSignature:
        return None


def _subscribe(db: DbSession, form: SignupForm, contact: Contact) -> None:
    contact.status = "subscribed"
    if form.list_id is not None:
        existing = db.scalar(
            select(ListMembership).where(ListMembership.list_id == form.list_id, ListMembership.contact_id == contact.id)
        )
        if existing is None:
            db.add(ListMembership(list_id=form.list_id, contact_id=contact.id, status="subscribed", subscribed_at=datetime.utcnow()))
        else:
            existing.status = "subscribed"
    db.commit()
    if form.list_id is not None:
        enroll_for_list(db, form.workspace_id, form.list_id, [contact.id])


def submit(db: DbSession, form: SignupForm, email: str, name: str = "") -> dict:
    """Handle a public form submission. Returns {status: 'pending'|'subscribed'}."""
    email = (email or "").strip().lower()
    if not is_valid_syntax(email):
        return {"status": "error", "detail": "Invalid email address"}

    contact = db.scalar(select(Contact).where(Contact.workspace_id == form.workspace_id, Contact.email == email))
    if contact is None:
        contact = Contact(workspace_id=form.workspace_id, email=email, name=name or None,
                          status="pending" if form.double_optin else "subscribed", source="signup_form")
        db.add(contact)
        db.commit()
        db.refresh(contact)

    domain = db.get(SendingDomain, form.sending_domain_id) if form.sending_domain_id else None
    if form.double_optin:
        # Double opt-in must NOT subscribe until confirmed. If no transport is
        # configured we can't send the confirmation — keep the contact pending and
        # signal a configuration problem rather than silently subscribing.
        if domain is None or not (domain.smtp_host or domain.api_key):
            return {"status": "pending", "detail": "confirmation email not configured"}
        link = f"{settings.base_url}/f/confirm/{make_token(form.id, email, name)}"
        html = f'<p>Please confirm your subscription:</p><p><a href="{link}">Confirm subscription</a></p>'
        try:
            provider = get_provider(domain)
            provider.open()
            provider.send(from_name="iceReach", from_email=f"confirm@{domain.domain}", to_email=email,
                          subject="Please confirm your subscription", html=html, text=f"Confirm: {link}")
            provider.close()
        except Exception:  # noqa: BLE001 — confirmation email best-effort
            pass
        return {"status": "pending"}

    # Single opt-in: subscribe immediately.
    _subscribe(db, form, contact)
    return {"status": "subscribed"}


def confirm(db: DbSession, token: str) -> bool:
    data = read_token(token)
    if not data:
        return False
    form = db.get(SignupForm, data.get("f"))
    if form is None:
        return False
    contact = db.scalar(select(Contact).where(Contact.workspace_id == form.workspace_id, Contact.email == data.get("e")))
    if contact is None:
        return False
    _subscribe(db, form, contact)
    return True
