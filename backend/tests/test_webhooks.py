from fastapi.testclient import TestClient

from icereach.db import SessionLocal
from icereach.main import app
from icereach.models import Campaign, Contact, Event, Message, Suppression, Workspace


def _seed(message_id="prov-1", email="r@x.com"):
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-wh"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email=email); camp = Campaign(workspace_id=ws.id, name="C")
        db.add_all([c, camp]); db.flush()
        m = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=c.id, status="sent", message_id=message_id)
        db.add(m); db.commit()
        return ws.id, camp.id, m.id
    finally:
        db.close()


def _events(message_id, etype):
    db = SessionLocal()
    try:
        return db.query(Event).filter(Event.message_id == message_id, Event.type == etype).count()
    finally:
        db.close()


def test_resend_delivered_records_event():
    _, _, mid = _seed("prov-del")
    c = TestClient(app)
    r = c.post("/webhooks/resend", json={"type": "email.delivered", "data": {"email_id": "prov-del", "to": ["r@x.com"]}})
    assert r.status_code == 200 and r.json()["received"] == 1
    assert _events(mid, "delivered") == 1


def test_resend_complaint_suppresses():
    ws_id, _, mid = _seed("prov-comp", "spammed@x.com")
    c = TestClient(app)
    r = c.post("/webhooks/resend", json={"type": "email.complained", "data": {"email_id": "prov-comp"}})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Suppression).filter(Suppression.email == "spammed@x.com", Suppression.reason == "complaint").count() == 1
    finally:
        db.close()


def test_sendgrid_bounce_marks_and_suppresses():
    ws_id, _, mid = _seed("sg-1", "bounced@x.com")
    c = TestClient(app)
    r = c.post("/webhooks/sendgrid", json=[{"event": "bounce", "email": "bounced@x.com", "sg_message_id": "sg-1"}])
    assert r.status_code == 200
    db = SessionLocal()
    try:
        m = db.get(Message, mid)
        assert m.status == "hard_bounce"
        assert db.query(Suppression).filter(Suppression.email == "bounced@x.com").count() == 1
    finally:
        db.close()


def test_email_only_event_does_not_cross_tenant_suppress():
    # A forged event with NO provider message id must not suppress anyone
    # (the workspace-unscoped email fallback was removed).
    _, _, _ = _seed("real-mid", "victim@x.com")
    c = TestClient(app)
    r = c.post("/webhooks/sendgrid", json=[{"event": "spamreport", "email": "victim@x.com"}])
    assert r.status_code == 200 and r.json()["received"] == 0
    db = SessionLocal()
    try:
        assert db.query(Suppression).filter(Suppression.email == "victim@x.com").count() == 0
    finally:
        db.close()


def test_delivered_unlocks_analytics_metric():
    from icereach.services.analytics import campaign_metrics
    ws_id, camp_id, mid = _seed("prov-an")
    c = TestClient(app)
    # before webhook -> delivered is None (no data)
    db = SessionLocal()
    try:
        assert campaign_metrics(db, ws_id, camp_id)["delivered"] is None
    finally:
        db.close()
    c.post("/webhooks/resend", json={"type": "email.delivered", "data": {"email_id": "prov-an"}})
    db = SessionLocal()
    try:
        assert campaign_metrics(db, ws_id, camp_id)["delivered"] == 1
    finally:
        db.close()
