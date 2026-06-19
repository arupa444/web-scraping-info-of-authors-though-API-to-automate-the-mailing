"""Reply tracking without an ESP: poll a sending domain's mailbox (POP3) and
match incoming replies to the messages we sent.

A reply carries the original ``Message-ID`` in its ``In-Reply-To`` / ``References``
headers. We sent that ``Message-ID`` (stored on ``Message.message_id``), so the
match is exact and tenant-safe — no cross-workspace email guessing.

POP3 is chosen because Zoho (and many providers) gate IMAP behind a paid plan
while leaving POP available. The poller is deliberately frugal:

* it runs ``UIDL`` first (a cheap list of stable per-message ids, no bodies);
* it ``RETR``s ONLY messages whose UID it hasn't processed before — so a message
  is downloaded at most once, never repeatedly;
* it NEVER ``DELE``s — the mailbox the user reads is left untouched;
* the per-domain "seen UID" set is pruned to what's still on the server, so it
  stays bounded and a message removed server-side is forgotten.

A reply is recorded at most once per sent message (dedup by ``message_id``), so
even a full re-scan can't double-count the "replies" metric.
"""

from __future__ import annotations

import email
import re
from email import policy

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Event, Message, SendingDomain
from .queue import register

# Cap the first sync of a large mailbox so we never download thousands at once.
_MAX_NEW_PER_POLL = 300

_MSGID_RE = re.compile(r"<[^<>@\s]+@[^<>@\s]+>")


def extract_reply_targets(raw: bytes | str) -> list[str]:
    """Return the Message-IDs an email is replying to (In-Reply-To + References)."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    msg = email.message_from_bytes(raw, policy=policy.default)
    ids: list[str] = []
    for header in ("In-Reply-To", "References"):
        value = msg.get(header)
        if value:
            ids.extend(_MSGID_RE.findall(value))
    # De-dupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for mid in ids:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def record_reply(db: DbSession, workspace_id: int, target_message_ids: list[str]) -> bool:
    """Match reply targets to one of our sent messages and record a reply Event.

    Idempotent: records at most one reply Event per sent message, so re-polling
    the same inbound email never inflates the count. Returns True if a NEW reply
    was recorded.
    """
    if not target_message_ids:
        return False
    msg = db.scalar(
        select(Message).where(
            Message.message_id.in_(target_message_ids),
            Message.workspace_id == workspace_id,
        )
    )
    if msg is None:
        return False
    already = db.scalar(
        select(Event).where(Event.message_id == msg.id, Event.type == "reply")
    )
    if already is not None:
        return False
    db.add(Event(workspace_id=workspace_id, message_id=msg.id, type="reply"))
    db.commit()
    return True


def poll_domain_pop3(db: DbSession, domain: SendingDomain) -> int:  # pragma: no cover - network
    """Download only new messages from the domain's POP3 mailbox and record replies."""
    import poplib

    seen: set[str] = set(domain.reply_seen_uids or [])
    client = poplib.POP3_SSL(domain.reply_host, domain.reply_port or 995, timeout=30)
    recorded = 0
    try:
        client.user(domain.reply_username)
        client.pass_(domain.reply_password)
        # UIDL: [b'1 <uid1>', b'2 <uid2>', ...] — cheap, no message bodies.
        _, uidl_lines, _ = client.uidl()
        pairs: list[tuple[int, str]] = []
        for line in uidl_lines:
            parts = line.decode("ascii", "replace").split(maxsplit=1)
            if len(parts) == 2:
                pairs.append((int(parts[0]), parts[1]))
        current = {uid for _, uid in pairs}
        # Newest first, then cap, so a big first sync stays bounded.
        new = [(num, uid) for num, uid in sorted(pairs, reverse=True) if uid not in seen][:_MAX_NEW_PER_POLL]

        # Start from prior seen that still exist on the server (prunes removed mail).
        processed = seen & current
        for num, uid in new:
            try:
                _, lines, _ = client.retr(num)
                raw = b"\r\n".join(lines)
                if record_reply(db, domain.workspace_id, extract_reply_targets(raw)):
                    recorded += 1
                processed.add(uid)  # mark seen only on successful processing
            except Exception:  # noqa: BLE001 — one bad message must not abort the batch
                db.rollback()
        domain.reply_seen_uids = sorted(processed)
        db.commit()
    finally:
        try:
            client.quit()  # QUIT (not DELE) — leaves all mail on the server
        except Exception:  # noqa: BLE001
            pass
    return recorded


def poll_domain(db: DbSession, domain: SendingDomain) -> int:  # pragma: no cover - dispatch
    if domain.reply_protocol == "pop3":
        return poll_domain_pop3(db, domain)
    return 0


def poll_all(db: DbSession) -> int:
    """Poll every domain with reply tracking enabled. Resilient per-domain."""
    domains = db.scalars(
        select(SendingDomain).where(SendingDomain.reply_protocol != "")
    ).all()
    total = 0
    for domain in domains:
        try:
            total += poll_domain(db, domain)
        except Exception:  # noqa: BLE001 — a flaky mailbox must not kill the worker tick
            db.rollback()
    return total


@register("poll_replies")
def poll_replies(db: DbSession, job, progress) -> dict:
    """Queue handler: poll all reply mailboxes once."""
    recorded = poll_all(db)
    return {"recorded": recorded}
