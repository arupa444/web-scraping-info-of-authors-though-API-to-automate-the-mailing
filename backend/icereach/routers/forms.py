"""Signup forms: authed CRUD + outbound webhooks CRUD + public form/confirm/archive."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Campaign, OutboundWebhook, SignupForm, Workspace
from ..schemas.growth import (
    OutboundWebhookIn,
    OutboundWebhookOut,
    SignupFormIn,
    SignupFormOut,
)
from ..security.deps import AuthContext, auth_context
from ..services import forms as forms_service

# ---- Authed: signup form CRUD ----
router = APIRouter(prefix="/api/forms", tags=["forms"])


def _form_out(f: SignupForm) -> SignupFormOut:
    return SignupFormOut(id=f.id, name=f.name, list_id=f.list_id, sending_domain_id=f.sending_domain_id,
                         double_optin=f.double_optin, success_message=f.success_message, redirect_url=f.redirect_url)


@router.post("", response_model=SignupFormOut, status_code=status.HTTP_201_CREATED)
def create_form(body: SignupFormIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    from ..models import ContactList, SendingDomain
    if body.list_id is not None and db.scalar(
        select(ContactList).where(ContactList.id == body.list_id, ContactList.workspace_id == ctx.workspace.id)
    ) is None:
        raise HTTPException(status_code=404, detail="List not found")
    if body.sending_domain_id is not None and db.scalar(
        select(SendingDomain).where(SendingDomain.id == body.sending_domain_id, SendingDomain.workspace_id == ctx.workspace.id)
    ) is None:
        raise HTTPException(status_code=404, detail="Sending domain not found")
    f = SignupForm(workspace_id=ctx.workspace.id, name=body.name, list_id=body.list_id,
                   sending_domain_id=body.sending_domain_id, double_optin=body.double_optin,
                   success_message=body.success_message, redirect_url=body.redirect_url)
    db.add(f)
    db.commit()
    db.refresh(f)
    return _form_out(f)


@router.get("", response_model=list[SignupFormOut])
def list_forms(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(SignupForm).where(SignupForm.workspace_id == ctx.workspace.id)).all()
    return [_form_out(f) for f in rows]


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(form_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    f = db.scalar(select(SignupForm).where(SignupForm.id == form_id, SignupForm.workspace_id == ctx.workspace.id))
    if f is None:
        raise HTTPException(status_code=404, detail="Form not found")
    db.delete(f)
    db.commit()


# ---- Authed: outbound webhook CRUD ----
hooks_router = APIRouter(prefix="/api/outbound-webhooks", tags=["outbound-webhooks"])


@hooks_router.post("", response_model=OutboundWebhookOut, status_code=status.HTTP_201_CREATED)
def create_hook(body: OutboundWebhookIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    h = OutboundWebhook(workspace_id=ctx.workspace.id, url=body.url, events=body.events, active=body.active)
    db.add(h)
    db.commit()
    db.refresh(h)
    return OutboundWebhookOut(id=h.id, url=h.url, events=h.events, active=h.active)


@hooks_router.get("", response_model=list[OutboundWebhookOut])
def list_hooks(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(OutboundWebhook).where(OutboundWebhook.workspace_id == ctx.workspace.id)).all()
    return [OutboundWebhookOut(id=h.id, url=h.url, events=h.events, active=h.active) for h in rows]


@hooks_router.delete("/{hook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hook(hook_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    h = db.scalar(select(OutboundWebhook).where(OutboundWebhook.id == hook_id, OutboundWebhook.workspace_id == ctx.workspace.id))
    if h is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(h)
    db.commit()


# ---- Public: hosted form, submit, confirm, archive (no auth) ----
public_router = APIRouter(tags=["public-growth"])


@public_router.get("/f/{form_id}", response_class=HTMLResponse)
def hosted_form(form_id: int, db: DbSession = Depends(get_db)):
    f = db.get(SignupForm, form_id)
    if f is None:
        return HTMLResponse("<p>Form not found.</p>", status_code=404)
    return HTMLResponse(
        f"""<!doctype html><html><body style="font-family:sans-serif;max-width:420px;margin:64px auto">
        <h2>{escape(f.name)}</h2>
        <form method="post" action="/f/{f.id}/submit">
          <input name="name" placeholder="Name" style="display:block;width:100%;padding:8px;margin:8px 0">
          <input name="email" type="email" required placeholder="Email" style="display:block;width:100%;padding:8px;margin:8px 0">
          <button type="submit" style="padding:10px 20px">Subscribe</button>
        </form></body></html>"""
    )


@public_router.post("/f/{form_id}/submit", response_class=HTMLResponse)
def submit_form(form_id: int, email: str = Form(...), name: str = Form(""), db: DbSession = Depends(get_db)):
    f = db.get(SignupForm, form_id)
    if f is None:
        return HTMLResponse("<p>Form not found.</p>", status_code=404)
    result = forms_service.submit(db, f, email, name)
    if result["status"] == "error":
        return HTMLResponse(f"<p>{escape(str(result.get('detail', 'Error')))}</p>", status_code=400)
    if result["status"] == "pending":
        return HTMLResponse("<p>Almost there — check your inbox to confirm your subscription.</p>")
    # Honor a configured redirect on success (only http/https).
    if f.redirect_url and f.redirect_url.startswith(("http://", "https://")):
        return RedirectResponse(f.redirect_url, status_code=303)
    return HTMLResponse(f"<p>{escape(f.success_message)}</p>")


@public_router.get("/f/confirm/{token}", response_class=HTMLResponse)
def confirm_form(token: str, db: DbSession = Depends(get_db)):
    ok = forms_service.confirm(db, token)
    return HTMLResponse("<p>Subscription confirmed. Thank you!</p>" if ok else "<p>Invalid or expired link.</p>",
                        status_code=200 if ok else 400)


@public_router.get("/a/{slug}", response_class=HTMLResponse)
def archive_index(slug: str, db: DbSession = Depends(get_db)):
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if ws is None:
        return HTMLResponse("<p>Not found.</p>", status_code=404)
    campaigns = db.scalars(
        select(Campaign).where(Campaign.workspace_id == ws.id, Campaign.status == "sent").order_by(Campaign.sent_at.desc())
    ).all()
    items = "".join(f'<li><a href="/a/{escape(slug)}/{c.id}">{escape(c.name)}</a></li>' for c in campaigns)
    return HTMLResponse(f"<!doctype html><html><body style='font-family:sans-serif;max-width:640px;margin:48px auto'>"
                        f"<h1>{escape(ws.name)} — Newsletter archive</h1><ul>{items or '<li>No issues yet.</li>'}</ul></body></html>")


@public_router.get("/a/{slug}/{campaign_id}", response_class=HTMLResponse)
def archive_issue(slug: str, campaign_id: int, db: DbSession = Depends(get_db)):
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if ws is None:
        return HTMLResponse("<p>Not found.</p>", status_code=404)
    camp = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.workspace_id == ws.id, Campaign.status == "sent"))
    if camp is None:
        return HTMLResponse("<p>Not found.</p>", status_code=404)
    from ..models import CampaignVariant
    variant = db.scalar(select(CampaignVariant).where(CampaignVariant.campaign_id == camp.id))
    return HTMLResponse(variant.html if variant else "<p>(no content)</p>")
