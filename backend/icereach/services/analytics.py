"""Campaign analytics: roll up Message + Event rows into deliverability metrics.

Phase 1 metrics are computed entirely from rows the platform already records:
sends and bounces from ``Message.status``; opens, clicks and unsubscribes from
``Event.type``.  ``delivered`` and ``complaints`` require ESP/feedback-loop
plumbing that does not exist yet, so they are reported as ``None`` rather than
a misleading zero.

Everything is workspace-scoped: the caller passes the tenant ``workspace_id``
and only rows belonging to that workspace (and the named campaign) are counted.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CampaignVariant, Event, Message


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Return numerator / denominator, or 0.0 when the denominator is zero."""
    if not denominator:
        return 0.0
    return numerator / denominator


def campaign_metrics(db: Session, workspace_id: int, campaign_id: int) -> dict:
    """Compute Phase 1 engagement metrics for a single campaign.

    All counts are scoped to ``workspace_id`` so one tenant can never observe
    another tenant's sends or events.

    Args:
        db: Active SQLAlchemy session.
        workspace_id: Owning workspace; isolates the query to this tenant.
        campaign_id: Campaign whose messages/events are aggregated.

    Returns:
        A dict with keys: ``sent``, ``hard_bounce``, ``soft_bounce``,
        ``unique_opens``, ``total_opens``, ``unique_clicks``, ``total_clicks``,
        ``ctr`` (total clicks / sent), ``ctor`` (unique clicks / unique opens),
        ``unsubscribes``, ``delivered`` (always ``None`` in Phase 1) and
        ``complaints`` (always ``None`` in Phase 1).
    """
    # --- Message-derived counts (sends + bounces), grouped by status. -------
    status_rows = db.execute(
        select(Message.status, func.count(Message.id))
        .where(
            Message.workspace_id == workspace_id,
            Message.campaign_id == campaign_id,
        )
        .group_by(Message.status)
    ).all()
    status_counts = {status: count for status, count in status_rows}

    sent = status_counts.get("sent", 0)
    hard_bounce = status_counts.get("hard_bounce", 0)
    soft_bounce = status_counts.get("soft_bounce", 0)

    # --- Event-derived counts, restricted to this campaign's messages. ------
    # Events carry their own workspace_id, but we additionally join back to
    # Message so we only count events for the messages in *this* campaign.
    def _event_counts(event_type: str) -> tuple[int, int]:
        """Return (total events, distinct message_ids) for an event type."""
        total, unique = db.execute(
            select(
                func.count(Event.id),
                func.count(func.distinct(Event.message_id)),
            )
            .select_from(Event)
            .join(Message, Message.id == Event.message_id)
            .where(
                Event.workspace_id == workspace_id,
                Event.type == event_type,
                Message.workspace_id == workspace_id,
                Message.campaign_id == campaign_id,
            )
        ).one()
        return int(total), int(unique)

    total_opens, unique_opens = _event_counts("open")
    total_clicks, unique_clicks = _event_counts("click")
    # Unsubscribes are reported as a flat count of unsubscribe events.
    unsubscribes, _ = _event_counts("unsubscribe")
    # Replies: one event per replied-to message (see services/replies.py), so the
    # unique count is the number of recipients who replied.
    _, replies = _event_counts("reply")

    # --- Derived ratios (guard divide-by-zero -> 0.0). ----------------------
    ctr = _safe_ratio(total_clicks, sent)
    ctor = _safe_ratio(unique_clicks, unique_opens)

    # delivered/complaints become real once ESP webhooks (P4) record them; until
    # any such signal exists we report None rather than a misleading zero.
    _, delivered_count = _event_counts("delivered")
    _, complaint_count = _event_counts("complaint")
    delivered: Optional[int] = delivered_count if delivered_count else None
    complaints: Optional[int] = complaint_count if complaint_count else None

    return {
        "sent": sent,
        "hard_bounce": hard_bounce,
        "soft_bounce": soft_bounce,
        "unique_opens": unique_opens,
        "total_opens": total_opens,
        "unique_clicks": unique_clicks,
        "total_clicks": total_clicks,
        "ctr": ctr,
        "ctor": ctor,
        "unsubscribes": unsubscribes,
        "replies": replies,
        "delivered": delivered,
        "complaints": complaints,
    }


def variant_breakdown(db: Session, workspace_id: int, campaign_id: int) -> dict:
    """Per-variant A/B stats + the current winner (by unique open rate)."""
    variants = db.scalars(
        select(CampaignVariant).where(CampaignVariant.campaign_id == campaign_id)
    ).all()
    rows = []
    for v in variants:
        sent = db.scalar(
            select(func.count(Message.id)).where(
                Message.campaign_id == campaign_id, Message.variant_id == v.id, Message.status == "sent"
            )
        ) or 0
        opens = db.scalar(
            select(func.count(func.distinct(Event.message_id)))
            .select_from(Event).join(Message, Message.id == Event.message_id)
            .where(Message.campaign_id == campaign_id, Message.variant_id == v.id, Event.type == "open")
        ) or 0
        clicks = db.scalar(
            select(func.count(func.distinct(Event.message_id)))
            .select_from(Event).join(Message, Message.id == Event.message_id)
            .where(Message.campaign_id == campaign_id, Message.variant_id == v.id, Event.type == "click")
        ) or 0
        rows.append({
            "variant_id": v.id, "subject": v.subject, "weight": v.weight,
            "sent": int(sent), "unique_opens": int(opens), "unique_clicks": int(clicks),
            "open_rate": _safe_ratio(int(opens), int(sent)),
            "click_rate": _safe_ratio(int(clicks), int(sent)),
        })
    winner = max(rows, key=lambda r: (r["open_rate"], r["click_rate"]), default=None)
    return {"variants": rows, "winner_variant_id": winner["variant_id"] if winner and winner["sent"] else None}
