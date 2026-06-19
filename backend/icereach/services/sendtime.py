"""Send-time optimization: pick the hour a contact is most likely to open.

Heuristic: the most common hour (UTC) of the contact's past opens; falls back to
a sensible workspace default when there's no history yet.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Event, Message

DEFAULT_HOUR = 10  # 10:00 UTC — reasonable global default before we have data


def best_hour(db: Session, contact_id: int, default: int = DEFAULT_HOUR) -> int:
    """Return the contact's best send hour (0-23) from past open events."""
    opens = db.scalars(
        select(Event.created_at)
        .select_from(Event)
        .join(Message, Message.id == Event.message_id)
        .where(Message.contact_id == contact_id, Event.type == "open")
    ).all()
    hours = [ts.hour for ts in opens if ts is not None]
    if not hours:
        return default
    return Counter(hours).most_common(1)[0][0]
