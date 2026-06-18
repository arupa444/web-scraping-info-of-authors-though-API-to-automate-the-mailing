from fastapi.testclient import TestClient

from icereach.ai import service as ai_service
from icereach.config import settings
from icereach.main import app


def _signup(email="ai@x.com", ws="AI"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_ai_subjects_503_when_disabled():
    c = _signup()
    r = c.post("/api/ai/subjects", json={"brief": "spring sale"}, headers=_csrf(c))
    assert r.status_code == 503


def test_ai_subjects_success_when_stubbed(monkeypatch):
    c = _signup("ai2@x.com", "AI2")
    monkeypatch.setattr(
        ai_service, "generate_subjects",
        lambda brief, n=5, tone="professional": [{"subject": "Hi", "preheader": "p", "rationale": "r"}],
    )
    r = c.post("/api/ai/subjects", json={"brief": "spring sale", "n": 1}, headers=_csrf(c))
    assert r.status_code == 200, r.text
    assert r.json()["variants"][0]["subject"] == "Hi"


def test_ai_requires_auth():
    c = TestClient(app)
    assert c.post("/api/ai/subjects", json={"brief": "x"}).status_code in (401, 403)
