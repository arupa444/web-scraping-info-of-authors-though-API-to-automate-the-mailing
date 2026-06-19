"""Campaigns: compose, send (background), analytics."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Campaign, CampaignVariant
from ..schemas.campaign import CampaignIn, CampaignOut, VariantIn, VariantOut
from ..security.deps import AuthContext, auth_context
from ..services import sender  # noqa: F401 — registers the send_campaign handler
from ..services.analytics import campaign_metrics, variant_breakdown
from ..services.queue import enqueue

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _out(db: DbSession, c: Campaign) -> CampaignOut:
    variants = db.scalars(select(CampaignVariant).where(CampaignVariant.campaign_id == c.id)).all()
    return CampaignOut(
        id=c.id, name=c.name, status=c.status, from_name=c.from_name, from_email=c.from_email,
        sending_domain_id=c.sending_domain_id, list_id=c.list_id, segment_id=c.segment_id,
        variants=[VariantOut(id=v.id, subject=v.subject, html=v.html, text=v.text, weight=v.weight) for v in variants],
    )


def _owned(db: DbSession, ctx: AuthContext, campaign_id: int) -> Campaign:
    c = db.scalar(select(Campaign).where(Campaign.id == campaign_id, Campaign.workspace_id == ctx.workspace.id))
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


def _validate_refs(db: DbSession, ctx: AuthContext, body: CampaignIn) -> None:
    """Reject references to another tenant's sending domain / list / segment."""
    from ..models import ContactList, Segment, SendingDomain
    checks = [
        (body.sending_domain_id, SendingDomain, "Sending domain"),
        (body.list_id, ContactList, "List"),
        (body.segment_id, Segment, "Segment"),
    ]
    for rid, model, label in checks:
        if rid is not None and db.scalar(
            select(model).where(model.id == rid, model.workspace_id == ctx.workspace.id)
        ) is None:
            raise HTTPException(status_code=404, detail=f"{label} not found")


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    _validate_refs(db, ctx, body)
    c = Campaign(
        workspace_id=ctx.workspace.id, name=body.name, from_name=body.from_name,
        from_email=str(body.from_email or ""), sending_domain_id=body.sending_domain_id,
        list_id=body.list_id, segment_id=body.segment_id, status="draft",
    )
    db.add(c)
    db.flush()
    variants = list(body.variants)
    # Seed a variant from a template when none were supplied explicitly.
    if not variants and body.template_id is not None:
        from ..models import Template
        tpl = db.scalar(select(Template).where(Template.id == body.template_id, Template.workspace_id == ctx.workspace.id))
        if tpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        variants = [VariantIn(subject=tpl.subject, html=tpl.html, text=tpl.text)]
    for v in variants:
        db.add(CampaignVariant(campaign_id=c.id, subject=v.subject, html=v.html, text=v.text, weight=v.weight))
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.get("", response_model=list[CampaignOut])
def list_campaigns(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(Campaign).where(Campaign.workspace_id == ctx.workspace.id).order_by(Campaign.id.desc())).all()
    return [_out(db, c) for c in rows]


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    return _out(db, _owned(db, ctx, campaign_id))


@router.post("/{campaign_id}/send")
def send(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    c = _owned(db, ctx, campaign_id)
    if c.status in ("sending", "sent"):
        raise HTTPException(status_code=409, detail=f"Campaign already {c.status}")
    if not db.scalar(select(CampaignVariant).where(CampaignVariant.campaign_id == c.id)):
        raise HTTPException(status_code=400, detail="Campaign has no content")
    if c.list_id is None and c.segment_id is None:
        raise HTTPException(status_code=400, detail="Campaign has no audience (list or segment)")
    if c.sending_domain_id is None:
        raise HTTPException(status_code=400, detail="Campaign has no sending domain")
    c.status = "scheduled"
    db.commit()
    job = enqueue(db, ctx.workspace.id, "send_campaign", {"campaign_id": c.id})
    from ..services.audit import log as audit_log
    audit_log(db, ctx.workspace.id, "campaign.sent", target=str(c.id), user_id=ctx.user.id)
    return {"job_id": job.id, "status_url": f"/api/jobs/{job.id}"}


@router.get("/{campaign_id}/analytics")
def analytics(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    _owned(db, ctx, campaign_id)
    return campaign_metrics(db, ctx.workspace.id, campaign_id)


@router.get("/{campaign_id}/variants")
def variants(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    _owned(db, ctx, campaign_id)
    return variant_breakdown(db, ctx.workspace.id, campaign_id)


def _narrative_payload(c: Campaign) -> dict:
    """Serialize a campaign's cached AI summary (empty if never generated)."""
    return {
        "summary": c.ai_summary or "",
        "highlights": list(c.ai_summary_highlights or []),
        # Naive UTC in the DB; tag it as UTC so the browser localizes correctly.
        "generated_at": (c.ai_summary_at.isoformat() + "Z") if c.ai_summary_at else None,
    }


@router.get("/{campaign_id}/analytics/narrative")
def get_analytics_narrative(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    """Return the persisted AI summary so it survives a refresh."""
    c = _owned(db, ctx, campaign_id)
    return _narrative_payload(c)


@router.post("/{campaign_id}/analytics/narrative")
def analytics_narrative(campaign_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    c = _owned(db, ctx, campaign_id)
    from ..ai import service as ai_service
    metrics = campaign_metrics(db, ctx.workspace.id, campaign_id)
    try:
        result = ai_service.summarize_analytics(metrics)
    except ai_service.AIDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    # Persist so the summary (and when it was generated) survives a refresh.
    c.ai_summary = result.get("summary", "")
    c.ai_summary_highlights = list(result.get("highlights", []))
    c.ai_summary_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return _narrative_payload(c)
