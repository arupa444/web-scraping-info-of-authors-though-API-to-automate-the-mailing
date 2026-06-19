from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.main import app
from icereach.routers import templates as tmpl_router


def _client(email="t@x.com", ws="T"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


BLOCKS = [
    {"type": "heading", "text": "Hi {name}", "level": 1},
    {"type": "text", "html": "<p>Welcome aboard</p>"},
    {"type": "button", "text": "Go", "url": "https://acme.com"},
]


def test_create_derives_html_and_text():
    c = _client()
    r = c.post("/api/templates", json={"name": "Welcome", "subject": "Hi {name}", "blocks": BLOCKS}, headers=_csrf(c))
    assert r.status_code == 201, r.text
    body = r.json()
    assert "<table" in body["html"] and "Hi {name}" in body["html"]
    assert "Welcome aboard" in body["text"]


def test_render_preview_without_save():
    c = _client("t2@x.com", "T2")
    r = c.post("/api/templates/render", json={"blocks": BLOCKS}, headers=_csrf(c))
    assert r.status_code == 200
    assert "<table" in r.json()["html"]


def test_test_send_uses_smtp(monkeypatch):
    sent = []

    class Fake:
        def __init__(self, *a, **k): pass
        def connect(self): pass
        def send(self, frm, to, msg): sent.append((frm, to))
        def close(self): pass

    monkeypatch.setattr(tmpl_router, "SmtpSession", Fake)
    c = _client("t3@x.com", "T3")
    h = _csrf(c)
    tid = c.post("/api/templates", json={"name": "W", "subject": "S", "blocks": BLOCKS}, headers=h).json()["id"]
    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    r = c.post(f"/api/templates/{tid}/test-send", json={"to_email": "me@x.com", "sending_domain_id": dom}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["sent"] is True
    assert sent and sent[0][1] == "me@x.com"


def test_campaign_from_template_seeds_variant():
    c = _client("t4@x.com", "T4")
    h = _csrf(c)
    tid = c.post("/api/templates", json={"name": "W", "subject": "Subj {name}", "blocks": BLOCKS}, headers=h).json()["id"]
    camp = c.post("/api/campaigns", json={"name": "C", "template_id": tid}, headers=h).json()
    assert len(camp["variants"]) == 1
    assert camp["variants"][0]["subject"] == "Subj {name}"
    assert "<table" in camp["variants"][0]["html"]


def test_saved_blocks_crud():
    c = _client("t5@x.com", "T5")
    h = _csrf(c)
    sb = c.post("/api/saved-blocks", json={"name": "CTA", "block": {"type": "button", "text": "Buy", "url": "x"}}, headers=h)
    assert sb.status_code == 201
    assert any(b["name"] == "CTA" for b in c.get("/api/saved-blocks").json())
