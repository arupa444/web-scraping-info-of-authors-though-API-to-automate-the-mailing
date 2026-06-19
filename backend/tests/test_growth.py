from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.db import SessionLocal
from icereach.main import app
from icereach.models import Contact
from icereach.services import esp, forms as forms_service, webhooks_out


class _FakeSmtp:
    def __init__(self, *a, **k): pass
    def connect(self): pass
    def send(self, *a, **k): return None
    def close(self): pass


def _client(email, ws):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_form_single_optin_subscribes():
    c = _client("g1@x.com", "G1")
    h = _csrf(c)
    lid = c.post("/api/lists", json={"name": "L"}, headers=h).json()["id"]
    fid = c.post("/api/forms", json={"name": "Join", "list_id": lid, "double_optin": False}, headers=h).json()["id"]
    r = c.post(f"/f/{fid}/submit", data={"email": "new@x.com", "name": "New"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        ct = db.query(Contact).filter(Contact.email == "new@x.com").first()
        assert ct is not None and ct.status == "subscribed"
    finally:
        db.close()


def test_form_double_optin_pending_then_confirm(monkeypatch):
    monkeypatch.setattr(esp, "SmtpSession", _FakeSmtp)
    c = _client("g2@x.com", "G2")
    h = _csrf(c)
    lid = c.post("/api/lists", json={"name": "L"}, headers=h).json()["id"]
    dom = c.post("/api/sending-domains", json={"domain": "m.g2.com", "smtp_host": "smtp.g2.com"}, headers=h).json()["domain"]["id"]
    fid = c.post("/api/forms", json={"name": "Join", "list_id": lid, "sending_domain_id": dom, "double_optin": True}, headers=h).json()["id"]
    r = c.post(f"/f/{fid}/submit", data={"email": "dbl@x.com"})
    assert "check your inbox" in r.text.lower()
    db = SessionLocal()
    try:
        ct = db.query(Contact).filter(Contact.email == "dbl@x.com").first()
        assert ct.status == "pending"
    finally:
        db.close()
    token = forms_service.make_token(fid, "dbl@x.com")
    conf = c.get(f"/f/confirm/{token}")
    assert conf.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(Contact).filter(Contact.email == "dbl@x.com").first().status == "subscribed"
    finally:
        db.close()


def test_v1_api_contacts_and_email(monkeypatch):
    monkeypatch.setattr(esp, "SmtpSession", _FakeSmtp)
    c = _client("g3@x.com", "G3")
    h = _csrf(c)
    token = c.post("/api/api-keys", json={"name": "ci"}, headers=h).json()["token"]
    dom = c.post("/api/sending-domains", json={"domain": "m.g3.com", "smtp_host": "smtp.g3.com"}, headers=h).json()["domain"]["id"]
    auth = {"Authorization": f"Bearer {token}"}
    # no key -> 401
    assert TestClient(app).get("/v1/contacts").status_code == 401
    cr = c.post("/v1/contacts", json={"email": "api@x.com", "name": "API"}, headers=auth)
    assert cr.status_code == 201, cr.text
    assert any(x["email"] == "api@x.com" for x in c.get("/v1/contacts", headers=auth).json())
    em = c.post("/v1/emails", json={"to": "rcpt@x.com", "subject": "Hi {name}", "html": "<p>x</p>", "sending_domain_id": dom}, headers=auth)
    assert em.status_code == 200 and em.json()["status"] == "sent"


def test_outbound_webhook_crud_and_dispatch(monkeypatch):
    c = _client("g4@x.com", "G4")
    h = _csrf(c)
    me = c.get("/api/auth/me").json()["workspace"]["id"]
    c.post("/api/outbound-webhooks", json={"url": "https://hooks.test/x", "events": "open,click"}, headers=h)
    assert len(c.get("/api/outbound-webhooks").json()) == 1
    calls = []
    monkeypatch.setattr(webhooks_out.httpx, "post", lambda url, json=None, timeout=None: calls.append(url))
    db = SessionLocal()
    try:
        n = webhooks_out.dispatch(db, me, "open", {"x": 1})
    finally:
        db.close()
    assert n == 1 and calls == ["https://hooks.test/x"]


def test_ai_narrative_endpoint(monkeypatch):
    from icereach.ai import service as ai_service
    c = _client("g5@x.com", "G5")
    h = _csrf(c)
    cid = c.post("/api/campaigns", json={"name": "C", "variants": [{"subject": "s", "html": "h"}]}, headers=h).json()["id"]
    monkeypatch.setattr(ai_service, "summarize_analytics", lambda m: {"summary": "Good open rate.", "highlights": ["x"]})
    r = c.post(f"/api/campaigns/{cid}/analytics/narrative", headers=h)
    assert r.status_code == 200 and r.json()["summary"] == "Good open rate."
