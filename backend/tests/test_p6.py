from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.db import SessionLocal
from icereach.main import app
from icereach.models import Workspace
from icereach.services import esp
from icereach.services.ratelimit import RateLimiter, limiter


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


def test_quota_blocks_transactional_send(monkeypatch):
    monkeypatch.setattr(esp, "SmtpSession", _FakeSmtp)
    c = _client("q@x.com", "Q")
    h = _csrf(c)
    ws_id = c.get("/api/auth/me").json()["workspace"]["id"]
    token = c.post("/api/api-keys", json={"name": "k"}, headers=h).json()["token"]
    dom = c.post("/api/sending-domains", json={"domain": "m.q.com", "smtp_host": "smtp.q.com"}, headers=h).json()["domain"]["id"]
    # set a hard limit of 1 send/month
    db = SessionLocal()
    try:
        db.get(Workspace, ws_id).monthly_send_limit = 1
        db.commit()
    finally:
        db.close()
    auth = {"Authorization": f"Bearer {token}"}
    payload = {"to": "a@x.com", "subject": "s", "html": "<p>x</p>", "sending_domain_id": dom}
    assert c.post("/v1/emails", json=payload, headers=auth).status_code == 200
    payload["to"] = "b@x.com"
    assert c.post("/v1/emails", json=payload, headers=auth).status_code == 429


def test_rate_limiter_unit():
    rl = RateLimiter()
    assert rl.allow("ip", 2, now=0.0)[0] is True
    assert rl.allow("ip", 2, now=0.0)[0] is True
    allowed, retry = rl.allow("ip", 2, now=0.0)
    assert allowed is False and retry > 0
    # different window resets
    assert rl.allow("ip", 2, now=120.0)[0] is True


def test_rate_limit_middleware_429(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    limiter.reset()
    try:
        c = TestClient(app)
        assert c.get("/api/auth/me").status_code in (200, 401)
        assert c.get("/api/auth/me").status_code in (200, 401)
        r = c.get("/api/auth/me")
        assert r.status_code == 429
        assert "Retry-After" in r.headers
    finally:
        limiter.reset()


def test_rbac_members_and_audit():
    owner = _client("owner@x.com", "RB")
    oh = _csrf(owner)
    # owner invites a member
    inv = owner.post("/api/members", json={"email": "member@x.com", "password": "memberpass1", "role": "member"}, headers=oh)
    assert inv.status_code == 201
    # member logs in and is forbidden from audit logs
    member = TestClient(app)
    member.post("/api/auth/login", json={"email": "member@x.com", "password": "memberpass1"})
    assert member.get("/api/audit-logs").status_code == 403
    # owner can read audit logs and sees the member.added entry
    logs = owner.get("/api/audit-logs")
    assert logs.status_code == 200
    assert any(x["action"] == "member.added" for x in logs.json())


def test_billing_checkout_applies_plan_and_rbac():
    owner = _client("b@x.com", "B6")
    oh = _csrf(owner)
    assert len(owner.get("/api/billing/plans").json()) == 3
    r = owner.post("/api/billing/checkout", json={"plan": "pro"}, headers=oh)
    assert r.status_code == 200 and r.json()["applied"] is True
    cur = owner.get("/api/billing").json()
    assert cur["plan"] == "pro" and cur["monthly_send_limit"] == 50000
    # a member cannot change billing
    owner.post("/api/members", json={"email": "m6@x.com", "password": "memberpass1", "role": "member"}, headers=oh)
    member = TestClient(app)
    member.post("/api/auth/login", json={"email": "m6@x.com", "password": "memberpass1"})
    assert member.post("/api/billing/checkout", json={"plan": "scale"},
                       headers={"X-CSRF-Token": member.cookies.get(settings.csrf_cookie)}).status_code == 403
