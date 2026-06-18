from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.db import SessionLocal
from icereach.main import app
from icereach.services import queue, sender


def _client(email="cf@x.com", ws="CF"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


class _FakeSmtp:
    def __init__(self, *a, **k): pass
    def connect(self): pass
    def send(self, *a, **k): pass
    def close(self): pass


def test_full_campaign_send_and_analytics(monkeypatch):
    monkeypatch.setattr(sender, "SmtpSession", _FakeSmtp)
    c = _client()
    h = _csrf(c)

    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    cid1 = c.post("/api/contacts", json={"email": "x1@t.com", "name": "X1"}, headers=h).json()["id"]
    cid2 = c.post("/api/contacts", json={"email": "x2@t.com", "name": "X2"}, headers=h).json()["id"]
    lid = c.post("/api/lists", json={"name": "All"}, headers=h).json()["id"]
    c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid1, cid2]}, headers=h)

    camp = c.post("/api/campaigns", json={
        "name": "Promo", "from_name": "Acme", "from_email": "hi@m.acme.com",
        "sending_domain_id": dom, "list_id": lid,
        "variants": [{"subject": "Hi {name}", "html": "<p>Hi {name}</p>"}],
    }, headers=h).json()
    camp_id = camp["id"]
    assert camp["status"] == "draft"

    send = c.post(f"/api/campaigns/{camp_id}/send", headers=h)
    assert send.status_code == 200, send.text
    job_id = send.json()["job_id"]

    # run the queued job inline (worker would normally do this)
    db = SessionLocal()
    try:
        job = queue.claim_next(db)
        assert job is not None and job.id == job_id
        queue.run_job(db, job)
    finally:
        db.close()

    # job done
    assert c.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    # analytics reflect 2 sent, delivered/complaints honestly None
    a = c.get(f"/api/campaigns/{camp_id}/analytics").json()
    assert a["sent"] == 2
    assert a["delivered"] is None
    assert a["complaints"] is None


def test_send_requires_audience_and_domain():
    c = _client("cf2@x.com", "CF2")
    h = _csrf(c)
    camp_id = c.post("/api/campaigns", json={"name": "Empty", "variants": [{"subject": "s", "html": "h"}]}, headers=h).json()["id"]
    r = c.post(f"/api/campaigns/{camp_id}/send", headers=h)
    assert r.status_code == 400
