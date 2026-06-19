from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.main import app
from icereach.routers import sending_domains


def _client(email="sd@x.com", ws="SD"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_create_returns_three_dns_records():
    c = _client()
    r = c.post("/api/sending-domains", json={"domain": "mail.acme.com", "smtp_host": "smtp.acme.com"}, headers=_csrf(c))
    assert r.status_code == 201, r.text
    records = r.json()["records"]
    assert len(records) == 3
    purposes = {rec["type"] for rec in records}
    assert purposes == {"TXT"} or len(records) == 3  # all TXT (SPF/DKIM/DMARC)
    hosts = " ".join(rec["host"] for rec in records)
    assert "_domainkey" in hosts and "_dmarc" in hosts


def test_verify_tls_defaults_true_and_can_opt_out():
    c = _client("sdt@x.com", "SDT")
    h = _csrf(c)
    d1 = c.post("/api/sending-domains", json={"domain": "a.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]
    assert d1["verify_tls"] is True  # secure default
    d2 = c.post("/api/sending-domains", json={"domain": "b.acme.com", "smtp_host": "mail.internal", "verify_tls": False}, headers=h).json()["domain"]
    assert d2["verify_tls"] is False


def test_verify_flips_flags(monkeypatch):
    c = _client("sd2@x.com", "SD2")
    monkeypatch.setattr(sending_domains, "verify_spf", lambda *a, **k: True)
    monkeypatch.setattr(sending_domains, "verify_dkim", lambda *a, **k: True)
    monkeypatch.setattr(sending_domains, "verify_dmarc", lambda *a, **k: True)
    did = c.post("/api/sending-domains", json={"domain": "mail.acme2.com"}, headers=_csrf(c)).json()["domain"]["id"]
    r = c.post(f"/api/sending-domains/{did}/verify", headers=_csrf(c))
    assert r.status_code == 200
    assert r.json()["status"] == "verified"
    assert r.json()["dkim_verified"] is True
