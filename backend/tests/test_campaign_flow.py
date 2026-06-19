from fastapi.testclient import TestClient

from icereach.config import settings
from icereach.db import SessionLocal
from icereach.main import app
from icereach.services import esp, queue, sender


def _client(email="cf@x.com", ws="CF"):
    c = TestClient(app)
    c.post("/api/auth/signup", json={"email": email, "password": "supersecret", "workspace_name": ws})
    return c


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get(settings.csrf_cookie)}


class _FakeSmtp:
    def __init__(self, *a, **k): pass
    def connect(self): pass
    def send(self, *a, **k): pass
    def close(self): pass


def test_full_campaign_send_and_analytics(monkeypatch):
    monkeypatch.setattr(esp, "SmtpSession", _FakeSmtp)
    c = _client()
    h = _csrf(c)

    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    cid1 = c.post("/api/contacts", json={"email": "x1@t.com", "name": "X1"}, headers=h).json()["id"]
    cid2 = c.post("/api/contacts", json={"email": "x2@t.com", "name": "X2"}, headers=h).json()["id"]
    lid = c.post("/api/lists", json={"name": "All"}, headers=h).json()["id"]
    c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid1, cid2]}, headers=h)

    camp = c.post("/api/campaigns", json={
        "name": "Promo", "from_name": "Acme", "from_email": "hi@m.acme.com",
        "sending_domain_id": dom, "list_id": lid,
        "variants": [{"subject": "Hi {name}", "html": "<p>Hi {name}</p>"}],
    }, headers=h).json()
    camp_id = camp["id"]
    assert camp["status"] == "draft"

    send = c.post(f"/api/campaigns/{camp_id}/send", headers=h)
    assert send.status_code == 200, send.text
    job_id = send.json()["job_id"]

    # run the queued job inline (worker would normally do this)
    db = SessionLocal()
    try:
        job = queue.claim_next(db)
        assert job is not None and job.id == job_id
        queue.run_job(db, job)
    finally:
        db.close()

    # job done
    assert c.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    # analytics reflect 2 sent, delivered/complaints honestly None
    a = c.get(f"/api/campaigns/{camp_id}/analytics").json()
    assert a["sent"] == 2
    assert a["delivered"] is None
    assert a["complaints"] is None


def test_send_requires_audience_and_domain():
    c = _client("cf2@x.com", "CF2")
    h = _csrf(c)
    camp_id = c.post("/api/campaigns", json={"name": "Empty", "variants": [{"subject": "s", "html": "h"}]}, headers=h).json()["id"]
    r = c.post(f"/api/campaigns/{camp_id}/send", headers=h)
    assert r.status_code == 400


def test_campaign_marked_failed_when_all_sends_fail(monkeypatch):
    # Every recipient send raises -> campaign must NOT show as 'sent'.
    class _Boom(_FakeSmtp):
        def send(self, *a, **k):
            raise RuntimeError("smtp blew up")
    monkeypatch.setattr(esp, "SmtpSession", _Boom)
    c = _client("cf3@x.com", "CF3")
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    cid = c.post("/api/contacts", json={"email": "z@t.com", "name": "Z"}, headers=h).json()["id"]
    lid = c.post("/api/lists", json={"name": "L"}, headers=h).json()["id"]
    c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid]}, headers=h)
    camp_id = c.post("/api/campaigns", json={
        "name": "Doomed", "from_name": "A", "from_email": "a@m.acme.com",
        "sending_domain_id": dom, "list_id": lid,
        "variants": [{"subject": "s", "html": "<p>h</p>"}],
    }, headers=h).json()["id"]
    c.post(f"/api/campaigns/{camp_id}/send", headers=h)
    db = SessionLocal()
    try:
        queue.run_job(db, queue.claim_next(db))
    finally:
        db.close()
    assert c.get(f"/api/campaigns/{camp_id}").json()["status"] == "failed"


def test_create_campaign_with_multiple_templates_seeds_one_variant_each():
    c = _client("cf4@x.com", "CF4")
    h = _csrf(c)
    t1 = c.post("/api/templates", json={"name": "T1", "subject": "One", "blocks": [{"type": "text", "html": "<p>1</p>"}]}, headers=h).json()["id"]
    t2 = c.post("/api/templates", json={"name": "T2", "subject": "Two", "blocks": [{"type": "text", "html": "<p>2</p>"}]}, headers=h).json()["id"]
    camp = c.post("/api/campaigns", json={"name": "Multi", "template_ids": [t1, t2]}, headers=h).json()
    subjects = sorted(v["subject"] for v in camp["variants"])
    assert subjects == ["One", "Two"]


def test_edit_campaign_updates_fields_and_replaces_variants():
    c = _client("cf6@x.com", "CF6")
    h = _csrf(c)
    lid = c.post("/api/lists", json={"name": "L"}, headers=h).json()["id"]
    camp = c.post("/api/campaigns", json={
        "name": "Before", "variants": [{"subject": "old", "html": "<p>old</p>"}],
    }, headers=h).json()
    cid = camp["id"]
    r = c.patch(f"/api/campaigns/{cid}", json={
        "name": "After", "list_id": lid,
        "variants": [{"subject": "new A", "html": "<p>a</p>"}, {"subject": "new B", "html": "<p>b</p>"}],
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "After" and body["list_id"] == lid
    assert sorted(v["subject"] for v in body["variants"]) == ["new A", "new B"]
    # Persisted.
    assert c.get(f"/api/campaigns/{cid}").json()["name"] == "After"


def test_edit_blocked_while_in_flight(monkeypatch):
    monkeypatch.setattr(esp, "SmtpSession", _FakeSmtp)
    c = _client("cf7@x.com", "CF7")
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    cid = c.post("/api/contacts", json={"email": "z@t.com"}, headers=h).json()["id"]
    lid = c.post("/api/lists", json={"name": "L"}, headers=h).json()["id"]
    c.post(f"/api/lists/{lid}/contacts", json={"contact_ids": [cid]}, headers=h)
    camp_id = c.post("/api/campaigns", json={
        "name": "C", "from_email": "a@m.acme.com", "sending_domain_id": dom, "list_id": lid,
        "variants": [{"subject": "s", "html": "<p>h</p>"}],
    }, headers=h).json()["id"]
    c.post(f"/api/campaigns/{camp_id}/send", headers=h)  # -> scheduled
    r = c.patch(f"/api/campaigns/{camp_id}", json={"name": "X", "variants": [{"subject": "s", "html": "h"}]}, headers=h)
    assert r.status_code == 409


def test_duplicate_campaign_to_new_list():
    c = _client("cf5@x.com", "CF5")
    h = _csrf(c)
    dom = c.post("/api/sending-domains", json={"domain": "m.acme.com", "smtp_host": "smtp.acme.com"}, headers=h).json()["domain"]["id"]
    list_a = c.post("/api/lists", json={"name": "A"}, headers=h).json()["id"]
    list_b = c.post("/api/lists", json={"name": "B"}, headers=h).json()["id"]
    src = c.post("/api/campaigns", json={
        "name": "Orig", "sending_domain_id": dom, "list_id": list_a,
        "variants": [{"subject": "s", "html": "<p>h</p>"}],
    }, headers=h).json()
    dup = c.post(f"/api/campaigns/{src['id']}/duplicate", json={"list_id": list_b}, headers=h)
    assert dup.status_code == 201, dup.text
    body = dup.json()
    assert body["id"] != src["id"]
    assert body["status"] == "draft"
    assert body["list_id"] == list_b               # re-targeted
    assert body["sending_domain_id"] == dom        # sender settings copied
    assert len(body["variants"]) == 1 and body["variants"][0]["subject"] == "s"
