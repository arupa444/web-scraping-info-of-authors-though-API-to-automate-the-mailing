from icereach.db import SessionLocal
from icereach.models import Campaign, Contact, Message, Suppression, Workspace
from icereach.services.dsn import parse_dsn, process_dsn_message

HARD_DSN = """From: MAILER-DAEMON@relay.test
To: bounce@mail.example.com
Subject: Delivery Status Notification (Failure)
Content-Type: multipart/report; report-type=delivery-status; boundary="BOUND"

--BOUND
Content-Type: text/plain

Your message could not be delivered.

--BOUND
Content-Type: message/delivery-status

Reporting-MTA: dns; relay.test

Final-Recipient: rfc822; gone@x.com
Action: failed
Status: 5.1.1

--BOUND
Content-Type: text/rfc822-headers

Message-ID: <orig-123@mail.example.com>
Subject: Hi

--BOUND--
"""


def test_parse_dsn_extracts_fields():
    info = parse_dsn(HARD_DSN)
    assert info["recipient"] == "gone@x.com"
    assert info["status"] == "5.1.1"
    assert info["is_hard"] is True
    assert info["original_message_id"] == "<orig-123@mail.example.com>"


def test_process_hard_bounce_suppresses():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-dsn")
        db.add(ws)
        db.flush()
        contact = Contact(workspace_id=ws.id, email="gone@x.com")
        camp = Campaign(workspace_id=ws.id, name="C")
        db.add_all([contact, camp])
        db.flush()
        msg = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id,
                      status="sent", message_id="<orig-123@mail.example.com>")
        db.add(msg)
        db.commit()
        mid = msg.id

        assert process_dsn_message(db, HARD_DSN) is True
        db.refresh(msg)
        assert msg.status == "hard_bounce"
        sup = db.query(Suppression).filter(Suppression.workspace_id == ws.id, Suppression.email == "gone@x.com").first()
        assert sup is not None and sup.reason == "hard_bounce"
    finally:
        db.close()
