from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.main import app


def _client():
    return TestClient(app)


def _csrf_headers(client):
    return {"X-CSRF-Token": client.cookies.get(settings.csrf_cookie)}


def test_signup_creates_session_and_workspace():
    c = _client()
    r = c.post("/api/auth/signup", json={"email": "a@x.com", "password": "supersecret", "workspace_name": "Acme"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "a@x.com"
    assert body["workspace"]["slug"] == "acme"
    assert body["role"] == "owner"
    assert c.cookies.get(settings.session_cookie)


def test_me_requires_session():
    c = _client()
    assert c.get("/api/auth/me").status_code == 401
    c.post("/api/auth/signup", json={"email": "b@x.com", "password": "supersecret", "workspace_name": "B"})
    assert c.get("/api/auth/me").status_code == 200


def test_login_wrong_password_401():
    c = _client()
    c.post("/api/auth/signup", json={"email": "c@x.com", "password": "supersecret", "workspace_name": "C"})
    c.post("/api/auth/logout", headers=_csrf_headers(c))
    r = c.post("/api/auth/login", json={"email": "c@x.com", "password": "wrong"})
    assert r.status_code == 401


def test_logout_clears_session():
    c = _client()
    c.post("/api/auth/signup", json={"email": "d@x.com", "password": "supersecret", "workspace_name": "D"})
    assert c.get("/api/auth/me").status_code == 200
    r = c.post("/api/auth/logout", headers=_csrf_headers(c))
    assert r.status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_csrf_required_for_mutations():
    c = _client()
    c.post("/api/auth/signup", json={"email": "e@x.com", "password": "supersecret", "workspace_name": "E"})
    # No CSRF header -> blocked
    assert c.post("/api/api-keys", json={"name": "k"}).status_code == 403
    # With CSRF header -> allowed
    r = c.post("/api/api-keys", json={"name": "k"}, headers=_csrf_headers(c))
    assert r.status_code == 201, r.text


def test_duplicate_email_409():
    c = _client()
    c.post("/api/auth/signup", json={"email": "f@x.com", "password": "supersecret", "workspace_name": "F"})
    c2 = _client()
    r = c2.post("/api/auth/signup", json={"email": "f@x.com", "password": "supersecret", "workspace_name": "F2"})
    assert r.status_code == 409
