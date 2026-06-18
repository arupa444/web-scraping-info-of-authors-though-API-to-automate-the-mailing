"""Bounce processing via DSN (Delivery Status Notification) messages.

Over SMTP, bounces arrive asynchronously to the return-path mailbox as
multipart/report messages. We parse the failed recipient + status and map the
bounce back to our Message via the original Message-ID embedded in the report —
which keeps attribution tenant-safe (no cross-workspace email guessing).
"""

from __future__ import annotations

import email
from email import policy

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..models import Contact, Event, Message, Suppression
from .queue import register


def parse_dsn(raw: bytes | str) -> dict:
    """Extract {recipient, status, action, original_message_id, is_hard} from a DSN."""
    if isinstance(raw, str):
        raw = raw.encode()
    msg = email.message_from_bytes(raw, policy=policy.default)

    recipient = status = action = original_message_id = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "message/delivery-status":
            for block in part.get_payload():
                if not hasattr(block, "get"):
                    continue
                if block.get("Final-Recipient"):
                    recipient = block.get("Final-Recipient").split(";")[-1].strip()
                if block.get("Status"):
                    status = block.get("Status").strip()
                if block.get("Action"):
                    action = block.get("Action").strip()
        elif ctype in ("message/rfc822", "text/rfc822-headers"):
            payload = part.get_payload()
            if isinstance(payload, list) and payload and hasattr(payload[0], "get"):
                original_message_id = payload[0].get("Message-ID")
            else:
                body = part.get_payload(decode=True) or b""
                original_message_id = email.message_from_bytes(body, policy=policy.default).get("Message-ID")

    return {
        "recipient": recipient,
        "status": status,
        "action": action,
        "original_message_id": (original_message_id or "").strip() or None,
        "is_hard": bool(status and status.startswith("5")),
    }


def process_dsn_message(db: DbSession, raw: bytes | str) -> bool:
    """Apply a single DSN to its Message: set bounce status + suppress on hard bounce."""
    info = parse_dsn(raw)
    msg = None
    if info["original_message_id"]:
        msg = db.scalar(select(Message).where(Message.message_id == info["original_message_id"]))
    if msg is None:
        return False

    msg.status = "hard_bounce" if info["is_hard"] else "soft_bounce"
    if info["is_hard"]:
        contact = db.get(Contact, msg.contact_id)
        if contact is not None:
            exists = db.scalar(
                select(Suppression).where(Suppression.workspace_id == msg.workspace_id, Suppression.email == contact.email)
            )
            if exists is None:
                db.add(Suppression(workspace_id=msg.workspace_id, email=contact.email, reason="hard_bounce"))
    db.add(Event(workspace_id=msg.workspace_id, message_id=msg.id, type="bounce"))
    db.commit()
    return True


@register("poll_dsn")
def poll_dsn(db: DbSession, job, progress) -> dict:  # pragma: no cover - network/IMAP
    """Queue handler: fetch unseen messages from the bounce mailbox and process them."""
    import imaplib

    if not settings.bounce_imap_host:
        return {"processed": 0, "note": "no bounce mailbox configured"}

    processed = 0
    imap = imaplib.IMAP4_SSL(settings.bounce_imap_host)
    try:
        imap.login(settings.bounce_imap_user, settings.bounce_imap_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        ids = data[0].split()
        for i, num in enumerate(ids):
            _, msg_data = imap.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            if process_dsn_message(db, raw):
                processed += 1
            imap.store(num, "+FLAGS", "\\Seen")
            progress((i + 1) / max(1, len(ids)) * 100, f"Processed {processed} bounces")
    finally:
        imap.logout()
    return {"processed": processed}
