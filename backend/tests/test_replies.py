"""Reply tracking: matching incoming replies to sent messages + the smart
POP3 poller that downloads each message at most once."""
import poplib

from icereach.db import SessionLocal
from icereach.models import Campaign, Contact, Event, Message, SendingDomain, Workspace
from icereach.services import replies
from icereach.services.analytics import campaign_metrics

SENT_MID = "<orig-123@influenceai.in>"

REPLY_RAW = (
    b"From: lead@example.com\r\n"
    b"To: team@influenceai.in\r\n"
    b"Subject: Re: Your offer\r\n"
    b"In-Reply-To: " + SENT_MID.encode() + b"\r\n"
    b"\r\n"
    b"Yes, I'm interested!\r\n"
)
UNRELATED_RAW = b"From: x@y.com\r\nSubject: newsletter\r\n\r\nhello\r\n"


def _seed():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-reply")
        db.add(ws)
        db.flush()
        contact = Contact(workspace_id=ws.id, email="lead@example.com")
        camp = Campaign(workspace_id=ws.id, name="C")
        db.add_all([contact, camp])
        db.flush()
        msg = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id,
                      status="sent", message_id=SENT_MID)
        db.add(msg)
        db.commit()
        return ws.id, camp.id, msg.id
    finally:
        db.close()


def test_extract_reply_targets():
    assert replies.extract_reply_targets(REPLY_RAW) == [SENT_MID]
    assert replies.extract_reply_targets(UNRELATED_RAW) == []


def test_record_reply_is_idempotent_and_counts_in_analytics():
    ws_id, camp_id, _ = _seed()
    db = SessionLocal()
    try:
        assert replies.record_reply(db, ws_id, [SENT_MID]) is True
        # Second time: same message already has a reply -> no double count.
        assert replies.record_reply(db, ws_id, [SENT_MID]) is False
        assert replies.record_reply(db, ws_id, ["<nope@x>"]) is False
        assert campaign_metrics(db, ws_id, camp_id)["replies"] == 1
    finally:
        db.close()


class _FakePOP3:
    """Records retr() calls so we can prove already-seen mail isn't re-fetched."""
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.retr_calls: list[int] = []
        _FakePOP3.instances.append(self)

    def user(self, u): pass
    def pass_(self, p): pass

    def uidl(self):
        return (b"+OK", [b"1 uidA", b"2 uidB"], 0)

    def retr(self, num):
        self.retr_calls.append(num)
        raw = REPLY_RAW if num == 1 else UNRELATED_RAW
        return (b"+OK", raw.split(b"\r\n"), len(raw))

    def quit(self): pass


def test_pop3_poll_downloads_each_message_once(monkeypatch):
    ws_id, camp_id, _ = _seed()
    _FakePOP3.instances = []
    monkeypatch.setattr(poplib, "POP3_SSL", _FakePOP3)

    db = SessionLocal()
    try:
        dom = SendingDomain(
            workspace_id=ws_id, domain="influenceai.in",
            dkim_private_key="x", dkim_public_key="y",
            reply_protocol="pop3", reply_host="pop.zoho.in", reply_port=995,
            reply_username="team@influenceai.in", reply_password="secret",
        )
        db.add(dom)
        db.commit()

        # First poll: both UIDs are new -> both fetched, one reply recorded.
        assert replies.poll_domain_pop3(db, dom) == 1
        assert sorted(_FakePOP3.instances[0].retr_calls) == [1, 2]
        assert set(dom.reply_seen_uids) == {"uidA", "uidB"}

        # Second poll: nothing new -> NO retr calls (no re-download), no double count.
        assert replies.poll_domain_pop3(db, dom) == 0
        assert _FakePOP3.instances[1].retr_calls == []
        assert campaign_metrics(db, ws_id, camp_id)["replies"] == 1
    finally:
        db.close()
