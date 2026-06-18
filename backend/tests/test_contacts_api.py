from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.db import SessionLocal
from icereach.main import app
from icereach.models import Job


def _signup(email, ws):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


def test_contact_crud_scoped():
    c = _signup("o1@x.com", "WS1")
    r = c.post("/api/contacts", json={"email": "lead@x.com", "name": "Lead"}, headers=_csrf(c))
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert c.get(f"/api/contacts/{cid}").json()["email"] == "lead@x.com"
    # duplicate -> 409
    assert c.post("/api/contacts", json={"email": "lead@x.com"}, headers=_csrf(c)).status_code == 409
    # update
    assert c.patch(f"/api/contacts/{cid}", json={"name": "Lead2"}, headers=_csrf(c)).json()["name"] == "Lead2"
    # list
    assert any(x["id"] == cid for x in c.get("/api/contacts").json())


def test_contact_tenant_isolation():
    a = _signup("a2@x.com", "A2")
    b = _signup("b2@x.com", "B2")
    cid = a.post("/api/contacts", json={"email": "shared@x.com"}, headers=_csrf(a)).json()["id"]
    # B cannot see A's contact
    assert b.get(f"/api/contacts/{cid}").status_code == 404


def test_lists_and_membership():
    c = _signup("o3@x.com", "WS3")
    cid = c.post("/api/contacts", json={"email": "m@x.com"}, headers=_csrf(c)).json()["id"]
    lid = c.post("/api/lists", json={"name": "Newsletter"}, headers=_csrf(c)).json()["id"]
    r = c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid]}, headers=_csrf(c))
    assert r.status_code == 200 and r.json()["added"] == 1
    # adding again is idempotent
    assert c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid]}, headers=_csrf(c)).json()["added"] == 0


def test_jobs_endpoint_scoped():
    c = _signup("o4@x.com", "WS4")
    me = c.get("/api/auth/me").json()
    ws_id = me["workspace"]["id"]
    db = SessionLocal()
    try:
        job = Job(workspace_id=ws_id, type="noop", status="done", progress=100, payload={}, result={"ok": True})
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()
    r = c.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["result"] == {"ok": True}
