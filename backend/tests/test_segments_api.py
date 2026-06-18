from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.main import app


def _client(email="sg@x.com", ws="SG"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_segment_create_and_preview():
    c = _client()
    h = _csrf(c)
    c.post("/api/contacts", json={"email": "us1@t.com", "attributes": {"country": "US"}}, headers=h)
    c.post("/api/contacts", json={"email": "ca1@t.com", "attributes": {"country": "CA"}}, headers=h)
    rules = {"all": [{"field": "attributes.country", "op": "eq", "value": "US"}]}
    sid = c.post("/api/segments", json={"name": "US", "rules": rules}, headers=h).json()["id"]
    prev = c.get(f"/api/segments/{sid}/preview").json()
    assert prev["count"] == 1
    assert prev["sample"] == ["us1@t.com"]


def test_segment_bad_rule_422():
    c = _client("sg2@x.com", "SG2")
    h = _csrf(c)
    sid = c.post("/api/segments", json={"name": "bad", "rules": {"all": [{"field": "email", "op": "??", "value": 1}]}}, headers=h).json()["id"]
    assert c.get(f"/api/segments/{sid}/preview").status_code == 422
