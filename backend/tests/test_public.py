from fastapi.testclient import TestClient

from icereach.db import SessionLocal
from icereach.main import app
from icereach.models import Campaign, Contact, Event, Message, Suppression, Workspace
from icereach.services.tracking import encode_token


def _seed_message():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-public")
        db.add(ws)
        db.flush()
        contact = Contact(workspace_id=ws.id, email="recip@x.com")
        camp = Campaign(workspace_id=ws.id, name="C")
        db.add_all([contact, camp])
        db.flush()
        msg = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id, status="sent")
        db.add(msg)
        db.commit()
        return ws.id, contact.id, msg.id
    finally:
        db.close()


def _events(message_id, etype):
    db = SessionLocal()
    try:
        return [e for e in db.query(Event).filter(Event.message_id == message_id, Event.type == etype).all()]
    finally:
        db.close()


def test_open_pixel_records_event():
    _, _, mid = _seed_message()
    token = encode_token(mid)
    c = TestClient(app)
    r = c.get(f"/t/o/{token}.png", headers={"user-agent": "Mozilla/5.0"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(_events(mid, "open")) == 1


def test_open_pixel_ignores_bots():
    _, _, mid = _seed_message()
    token = encode_token(mid)
    c = TestClient(app)
    c.get(f"/t/o/{token}.png", headers={"user-agent": "facebookexternalhit/1.1"})
    assert len(_events(mid, "open")) == 0


def test_open_pixel_counts_gmail_image_proxy():
    # Gmail fetches the pixel through GoogleImageProxy on a real open; it must be
    # counted, not discarded as a bot.
    _, _, mid = _seed_message()
    token = encode_token(mid)
    c = TestClient(app)
    ua = "Mozilla/5.0 (via ggpht.com GoogleImageProxy)"
    r = c.get(f"/t/o/{token}.png", headers={"user-agent": ua})
    assert r.status_code == 200
    assert len(_events(mid, "open")) == 1


def test_click_redirects_and_records():
    _, _, mid = _seed_message()
    token = encode_token(mid, "https://example.com/landing")
    c = TestClient(app)
    r = c.get(f"/t/c/{token}", headers={"user-agent": "Mozilla/5.0"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/landing"
    assert len(_events(mid, "click")) == 1


def test_unsubscribe_get_is_safe_shows_confirmation_only():
    # Opening the link (or a scanner/prefetch GET) must NOT unsubscribe — it only
    # renders the confirmation page. The unsubscribe reflects only on POST.
    ws_id, _, mid = _seed_message()
    token = encode_token(mid)
    c = TestClient(app)
    r = c.get(f"/u/{token}")
    assert r.status_code == 200
    assert "Confirm unsubscribe" in r.text
    db = SessionLocal()
    try:
        assert db.query(Suppression).filter(Suppression.workspace_id == ws_id).count() == 0
        assert len(_events(mid, "unsubscribe")) == 0
    finally:
        db.close()


def test_unsubscribe_suppresses_contact():
    ws_id, _, mid = _seed_message()
    token = encode_token(mid)
    c = TestClient(app)
    r = c.post(f"/u/{token}")
    assert r.status_code == 200
    db = SessionLocal()
    try:
        sup = db.query(Suppression).filter(Suppression.workspace_id == ws_id, Suppression.email == "recip@x.com").first()
        assert sup is not None and sup.reason == "unsubscribe"
    finally:
        db.close()
