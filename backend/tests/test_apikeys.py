from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.main import app
from icereach.models import Workspace
from icereach.security import apikeys


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_apikey_generate_and_verify(db):
    ws = Workspace(name="W", slug="w-apikey")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    row, token = apikeys.generate(db, ws.id, "primary")
    assert token.startswith("ice_")
    resolved = apikeys.verify(db, token)
    assert resolved is not None and resolved.id == row.id
    assert apikeys.verify(db, "ice_bogus_xyz") is None


def test_apikey_revoke_blocks_verify(db):
    from datetime import datetime
    ws = Workspace(name="W2", slug="w-apikey2")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    row, token = apikeys.generate(db, ws.id, "k")
    row.revoked_at = datetime.utcnow()
    db.commit()
    assert apikeys.verify(db, token) is None


def test_apikey_crud_endpoints():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": "k@x.com", "password": "supersecret", "workspace_name": "K"})
    created = c.post("/api/api-keys", json={"name": "ci"}, headers=_csrf(c))
    assert created.status_code == 201, created.text
    assert created.json()["token"].startswith("ice_")
    key_id = created.json()["id"]

    listed = c.get("/api/api-keys")
    assert listed.status_code == 200
    assert any(k["id"] == key_id for k in listed.json())

    deleted = c.delete(f"/api/api-keys/{key_id}", headers=_csrf(c))
    assert deleted.status_code == 204
    assert all(k["id"] != key_id for k in c.get("/api/api-keys").json())
