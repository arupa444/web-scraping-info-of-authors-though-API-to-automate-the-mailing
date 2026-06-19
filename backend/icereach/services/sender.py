"""Campaign send job: resolve audience, suppress, render+track, DKIM-sign, send.

Registered as the 'send_campaign' queue handler. Idempotent: one Message per
(campaign, contact) — re-running a partially-sent campaign resumes safely.
"""

from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import (
    Campaign,
    CampaignVariant,
    Contact,
    ListMembership,
    Message,
    SendingDomain,
    Suppression,
)
from .esp import get_provider
from .merge import html_to_text, render
from .queue import register
from .segments import evaluate as evaluate_segment
from .tracking import encode_token, rewrite_html


def _recipients(db: DbSession, campaign: Campaign) -> list[Contact]:
    if campaign.list_id is not None:
        rows = db.scalars(
            select(Contact)
            .join(ListMembership, ListMembership.contact_id == Contact.id)
            .where(
                ListMembership.list_id == campaign.list_id,
                ListMembership.status == "subscribed",
                Contact.workspace_id == campaign.workspace_id,
                Contact.status == "subscribed",
            )
        ).all()
        return list(rows)
    if campaign.segment_id is not None:
        from ..models import Segment
        seg = db.get(Segment, campaign.segment_id)
        if seg is None:
            return []
        return [c for c in evaluate_segment(db, campaign.workspace_id, seg.rules) if c.status == "subscribed"]
    return []


def _pick_variant(variants: list[CampaignVariant]) -> CampaignVariant:
    weights = [max(1, v.weight) for v in variants]
    return random.choices(variants, weights=weights, k=1)[0]


def send_campaign(db: DbSession, job, progress) -> dict:
    campaign = db.get(Campaign, job.payload["campaign_id"])
    if campaign is None or campaign.workspace_id != job.workspace_id:
        raise ValueError("Campaign not found")

    variants = db.scalars(select(CampaignVariant).where(CampaignVariant.campaign_id == campaign.id)).all()
    if not variants:
        raise ValueError("Campaign has no content variants")

    domain = db.get(SendingDomain, campaign.sending_domain_id) if campaign.sending_domain_id else None
    if domain is None or not domain.smtp_host:
        raise ValueError("Campaign has no configured sending domain / SMTP relay")

    campaign.status = "sending"
    db.commit()

    recipients = _recipients(db, campaign)
    suppressed = {
        s.email for s in db.scalars(
            select(Suppression).where(Suppression.workspace_id == campaign.workspace_id)
        ).all()
    }

    from . import quota
    from ..models import Workspace
    workspace = db.get(Workspace, campaign.workspace_id)
    quota_remaining = quota.remaining(db, workspace)  # None = unlimited

    provider = get_provider(domain)
    provider.open()
    sent = 0
    skipped = 0
    total = len(recipients)
    try:
        for i, contact in enumerate(recipients):
            if quota_remaining is not None and sent >= quota_remaining:
                skipped += 1
                continue  # monthly quota reached — skip the remainder
            if contact.email in suppressed:
                skipped += 1
                continue
            # Idempotency: one message per (campaign, contact).
            if db.scalar(select(Message).where(Message.campaign_id == campaign.id, Message.contact_id == contact.id)):
                skipped += 1
                continue

            variant = _pick_variant(variants)
            msg_row = Message(
                workspace_id=campaign.workspace_id, campaign_id=campaign.id,
                contact_id=contact.id, variant_id=variant.id, status="queued",
            )
            db.add(msg_row)
            db.flush()  # assign id for tracking tokens

            row = {"name": contact.name or "", "email": contact.email, **(contact.attributes or {})}
            subject = render(variant.subject, row)
            html = rewrite_html(render(variant.html, row), msg_row.id)
            text = render(variant.text or html_to_text(variant.html), row)
            unsub_url = f"{settings.base_url}/u/{encode_token(msg_row.id)}"
            try:
                provider_id = provider.send(
                    from_name=campaign.from_name, from_email=campaign.from_email, to_email=contact.email,
                    subject=subject, html=html, text=text, list_unsub_url=unsub_url,
                )
                msg_row.status = "sent"
                msg_row.sent_at = datetime.utcnow()
                msg_row.message_id = provider_id
                sent += 1
            except Exception as exc:  # noqa: BLE001 — record per-recipient failure, keep going
                msg_row.status = "failed"
                msg_row.error = str(exc)
            db.commit()
            if total:
                progress((i + 1) / total * 100, f"Sent {sent}/{total}")
    finally:
        provider.close()

    campaign.status = "sent"
    campaign.sent_at = datetime.utcnow()
    db.commit()
    return {"sent": sent, "skipped": skipped, "recipients": total}


register("send_campaign")(send_campaign)
