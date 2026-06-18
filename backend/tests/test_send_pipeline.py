import pytest

from icereach.db import SessionLocal
from icereach.models import (
    Campaign,
    CampaignVariant,
    Contact,
    ContactList,
    ListMembership,
    Job,
    Message,
    SendingDomain,
    Suppression,
    Workspace,
)
from icereach.services import sender


class FakeSmtp:
    sent: list = []

    def __init__(self, *a, **k):
        pass

    def connect(self):
        pass

    def send(self, frm, to, msg):
        FakeSmtp.sent.append((frm, to, msg))

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _stub_smtp(monkeypatch):
    FakeSmtp.sent = []
    monkeypatch.setattr(sender, "SmtpSession", FakeSmtp)


def _seed(db, emails=("a@x.com", "b@x.com")):
    ws = Workspace(name="W", slug="w-send")
    db.add(ws)
    db.flush()
    domain = SendingDomain(
        workspace_id=ws.id, domain="mail.example.com", dkim_selector="ir1",
        dkim_private_key="x", dkim_public_key="v=DKIM1; k=rsa; p=AAA",
        smtp_host="smtp.relay.test", smtp_port=587, smtp_username="u", smtp_password="p",
        dkim_verified=False,
    )
    lst = ContactList(workspace_id=ws.id, name="L")
    db.add_all([domain, lst])
    db.flush()
    contacts = []
    for e in emails:
        c = Contact(workspace_id=ws.id, email=e, name=e.split("@")[0], status="subscribed")
        db.add(c)
        db.flush()
        db.add(ListMembership(list_id=lst.id, contact_id=c.id, status="subscribed"))
        contacts.append(c)
    camp = Campaign(
        workspace_id=ws.id, name="Launch", status="draft", sending_domain_id=domain.id,
        from_name="Acme", from_email="hi@mail.example.com", list_id=lst.id,
    )
    db.add(camp)
    db.flush()
    db.add(CampaignVariant(campaign_id=camp.id, subject="Hi {name}", html="<p>Hello {name} <a href='https://acme.com'>shop</a></p>"))
    db.commit()
    return ws.id, camp.id, contacts


def _run(db, ws_id, campaign_id):
    job = Job(workspace_id=ws_id, type="send_campaign", status="running", payload={"campaign_id": campaign_id})
    db.add(job)
    db.commit()
    db.refresh(job)
    return sender.send_campaign(db, job, lambda *a, **k: None)


def test_send_creates_messages_with_tracking():
    db = SessionLocal()
    try:
        ws_id, cid, contacts = _seed(db)
        result = _run(db, ws_id, cid)
        assert result["sent"] == 2
        msgs = db.query(Message).filter(Message.campaign_id == cid).all()
        assert len(msgs) == 2 and all(m.status == "sent" for m in msgs)
        # tracking + unsubscribe injected
        wire = FakeSmtp.sent[0][2].as_string()
        assert "/t/o/" in wire  # open pixel
        assert "/t/c/" in wire  # click rewrite
        assert "List-Unsubscribe" in wire
    finally:
        db.close()


def test_send_is_idempotent():
    db = SessionLocal()
    try:
        ws_id, cid, _ = _seed(db)
        _run(db, ws_id, cid)
        FakeSmtp.sent = []
        result = _run(db, ws_id, cid)
        assert result["sent"] == 0  # nothing re-sent
        assert db.query(Message).filter(Message.campaign_id == cid).count() == 2
    finally:
        db.close()


def test_send_skips_suppressed():
    db = SessionLocal()
    try:
        ws_id, cid, contacts = _seed(db)
        db.add(Suppression(workspace_id=ws_id, email="a@x.com", reason="unsubscribe"))
        db.commit()
        result = _run(db, ws_id, cid)
        assert result["sent"] == 1
        assert result["skipped"] >= 1
    finally:
        db.close()
