from fastapi.testclient import TestClient

from icereach.ai import service as ai_service
from icereach.config import settings
from icereach.main import app


def _client(email="au@x.com", ws="AU"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_automation_crud_and_activate():
    c = _client()
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.x.com", "smtp_host": "smtp.x.com"}, headers=h).json()["domain"]["id"]
    body = {
        "name": "Welcome series", "trigger_type": "manual", "sending_domain_id": dom,
        "from_name": "Acme", "from_email": "hi@m.x.com",
        "steps": [
            {"type": "send", "config": {"subject": "Hi {name}", "html": "<p>1</p>"}},
            {"type": "wait", "config": {"delay_days": 2}},
            {"type": "send", "config": {"subject": "Bye", "html": "<p>2</p>"}},
        ],
    }
    r = c.post("/api/automations", json=body, headers=h)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert len(r.json()["steps"]) == 3
    act = c.post(f"/api/automations/{aid}/activate", headers=h)
    assert act.status_code == 200 and act.json()["status"] == "active"


def test_manual_enroll_creates_run():
    c = _client("au2@x.com", "AU2")
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.x.com", "smtp_host": "smtp.x.com"}, headers=h).json()["domain"]["id"]
    cid = c.post("/api/contacts", json={"email": "lead@x.com"}, headers=h).json()["id"]
    aid = c.post("/api/automations", json={
        "name": "A", "sending_domain_id": dom, "from_email": "hi@m.x.com",
        "steps": [{"type": "send", "config": {"subject": "x", "html": "y"}}],
    }, headers=h).json()["id"]
    c.post(f"/api/automations/{aid}/activate", headers=h)
    r = c.post(f"/api/automations/{aid}/enroll", json={"contact_ids": [cid]}, headers=h)
    assert r.status_code == 200 and r.json()["enrolled"] == 1
    runs = c.get(f"/api/automations/{aid}/runs").json()
    assert len(runs) == 1 and runs[0]["contact_id"] == cid


def test_list_subscribe_auto_enrolls():
    c = _client("au3@x.com", "AU3")
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.x.com", "smtp_host": "smtp.x.com"}, headers=h).json()["domain"]["id"]
    lid = c.post("/api/lists", json={"name": "Newsletter"}, headers=h).json()["id"]
    aid = c.post("/api/automations", json={
        "name": "OnJoin", "trigger_type": "list_subscribe", "trigger_list_id": lid,
        "sending_domain_id": dom, "from_email": "hi@m.x.com",
        "steps": [{"type": "send", "config": {"subject": "x", "html": "y"}}],
    }, headers=h).json()["id"]
    c.post(f"/api/automations/{aid}/activate", headers=h)
    cid = c.post("/api/contacts", json={"email": "joiner@x.com"}, headers=h).json()["id"]
    c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid]}, headers=h)
    runs = c.get(f"/api/automations/{aid}/runs").json()
    assert len(runs) == 1  # auto-enrolled on subscribe


def test_ai_sequence_endpoint(monkeypatch):
    c = _client("au4@x.com", "AU4")
    h = _csrf(c)
    monkeypatch.setattr(ai_service, "draft_sequence",
                        lambda goal, steps=3: [{"subject": "S1", "html": "<p>1</p>", "wait_days": 0}])
    r = c.post("/api/ai/sequence", json={"goal": "onboard new users", "steps": 1}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["emails"][0]["subject"] == "S1"
