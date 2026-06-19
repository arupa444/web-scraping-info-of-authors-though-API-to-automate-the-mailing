"""Email templates + block builder: CRUD, render (live preview), test send, saved blocks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import SavedBlock, SendingDomain, Template
from ..schemas.template import (
    RenderIn,
    RenderOut,
    SavedBlockIn,
    SavedBlockOut,
    TemplateIn,
    TemplateOut,
    TestSendIn,
)
from ..security.deps import AuthContext, auth_context
from ..services.blocks import blocks_to_text, render_blocks
from ..services.merge import render
from ..services.smtp import SmtpSession, build_message, dkim_sign_message

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _out(t: Template) -> TemplateOut:
    return TemplateOut(id=t.id, name=t.name, subject=t.subject, blocks=t.blocks or [], html=t.html, text=t.text)


def _owned(db: DbSession, ctx: AuthContext, template_id: int) -> Template:
    t = db.scalar(select(Template).where(Template.id == template_id, Template.workspace_id == ctx.workspace.id))
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("/render", response_model=RenderOut)
def render_preview(body: RenderIn, ctx: AuthContext = Depends(auth_context)):
    """Render arbitrary blocks to HTML for live preview (no persistence)."""
    return RenderOut(html=render_blocks(body.blocks, preheader=body.preheader), text=blocks_to_text(body.blocks))


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    t = Template(
        workspace_id=ctx.workspace.id, name=body.name, subject=body.subject, blocks=body.blocks,
        html=render_blocks(body.blocks), text=blocks_to_text(body.blocks),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.get("", response_model=list[TemplateOut])
def list_templates(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Template).where(Template.workspace_id == ctx.workspace.id).order_by(Template.id.desc())).all()
    return [_out(t) for t in rows]


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    return _out(_owned(db, ctx, template_id))


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, body: TemplateIn, ctx: AuthContext = Depends(auth_context),
                    db: DbSession = Depends(get_db)):
    t = _owned(db, ctx, template_id)
    t.name = body.name
    t.subject = body.subject
    t.blocks = body.blocks
    t.html = render_blocks(body.blocks)
    t.text = blocks_to_text(body.blocks)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    db.delete(_owned(db, ctx, template_id))
    db.commit()


@router.get("/{template_id}/render", response_model=RenderOut)
def render_template(template_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    t = _owned(db, ctx, template_id)
    return RenderOut(html=t.html, text=t.text)


# NOTE: `def` (not async) so FastAPI runs the blocking SMTP send in a threadpool.
@router.post("/{template_id}/test-send")
def test_send(template_id: int, body: TestSendIn, ctx: AuthContext = Depends(auth_context),
              db: DbSession = Depends(get_db)):
    t = _owned(db, ctx, template_id)
    domain = db.scalar(
        select(SendingDomain).where(SendingDomain.id == body.sending_domain_id, SendingDomain.workspace_id == ctx.workspace.id)
    )
    if domain is None:
        raise HTTPException(status_code=404, detail="Sending domain not found")
    if not domain.smtp_host:
        raise HTTPException(status_code=400, detail="Sending domain has no SMTP relay configured")

    sample = {"name": "there", "email": str(body.to_email)}
    subject = render(body.subject or t.subject or "Test email", sample)
    html = render(t.html or render_blocks(t.blocks), sample)
    text = render(t.text or blocks_to_text(t.blocks), sample)
    from_email = f"test@{domain.domain}"
    msg = build_message(ctx.workspace.name, from_email, str(body.to_email), f"[TEST] {subject}", html, text)

    session = SmtpSession(domain.smtp_host, domain.smtp_port, domain.smtp_username, domain.smtp_password)
    try:
        session.connect()
        if domain.dkim_verified:
            session.send(from_email, str(body.to_email), dkim_sign_message(msg, domain.domain, domain.dkim_selector, domain.dkim_private_key))
        else:
            session.send(from_email, str(body.to_email), msg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Test send failed: {exc}")
    finally:
        session.close()
    return {"sent": True, "to": str(body.to_email)}


# ---- Saved (reusable) blocks ----
saved_router = APIRouter(prefix="/api/saved-blocks", tags=["saved-blocks"])


@saved_router.post("", response_model=SavedBlockOut, status_code=status.HTTP_201_CREATED)
def create_saved_block(body: SavedBlockIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    sb = SavedBlock(workspace_id=ctx.workspace.id, name=body.name, block=body.block)
    db.add(sb)
    db.commit()
    db.refresh(sb)
    return SavedBlockOut(id=sb.id, name=sb.name, block=sb.block)


@saved_router.get("", response_model=list[SavedBlockOut])
def list_saved_blocks(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(SavedBlock).where(SavedBlock.workspace_id == ctx.workspace.id)).all()
    return [SavedBlockOut(id=s.id, name=s.name, block=s.block) for s in rows]


@saved_router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_block(block_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    sb = db.scalar(select(SavedBlock).where(SavedBlock.id == block_id, SavedBlock.workspace_id == ctx.workspace.id))
    if sb is None:
        raise HTTPException(status_code=404, detail="Saved block not found")
    db.delete(sb)
    db.commit()
