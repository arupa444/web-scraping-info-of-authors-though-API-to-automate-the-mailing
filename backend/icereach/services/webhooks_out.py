"""Outbound webhooks: POST workspace events to subscriber URLs (best-effort)."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import OutboundWebhook


def dispatch(db: DbSession, workspace_id: int, event: str, payload: dict) -> int:
    """Fire an event to all active webhooks in the workspace subscribed to it.

    Returns the number of endpoints attempted. Failures are swallowed (delivery is
    best-effort; a real system would queue + retry).
    """
    hooks = db.scalars(
        select(OutboundWebhook).where(OutboundWebhook.workspace_id == workspace_id, OutboundWebhook.active.is_(True))
    ).all()
    attempted = 0
    body = {"event": event, "data": payload}
    for hook in hooks:
        subscribed = not hook.events or event in {e.strip() for e in hook.events.split(",") if e.strip()}
        if not subscribed:
            continue
        attempted += 1
        try:
            httpx.post(hook.url, json=body, timeout=10)
        except Exception:  # noqa: BLE001
            pass
    return attempted
