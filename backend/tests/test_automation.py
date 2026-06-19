from datetime import datetime, timedelta

import pytest

from icereach.db import SessionLocal
from icereach.models import (
    Automation,
    AutomationRun,
    AutomationStep,
    Contact,
    Message,
    SendingDomain,
    Workspace,
)
from icereach.services import automation as engine
from icereach.services import esp


class FakeSmtp:
    sent: list = []

    def __init__(self, *a, **k): pass
    def connect(self): pass
    def send(self, frm, to, msg): FakeSmtp.sent.append(to)
    def close(self): pass


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    FakeSmtp.sent = []
    monkeypatch.setattr(esp, "SmtpSession", FakeSmtp)


def _domain(db, ws):
    d = SendingDomain(workspace_id=ws.id, domain="m.x.com", dkim_selector="s",
                      dkim_private_key="k", dkim_public_key="p", smtp_host="smtp.x.com",
                      smtp_port=587, smtp_username="u", smtp_password="p")
    db.add(d); db.flush()
    return d


def _automation(db, ws, domain, steps, status="active", trigger="manual", list_id=None):
    a = Automation(workspace_id=ws.id, name="A", status=status, trigger_type=trigger,
                   trigger_list_id=list_id, sending_domain_id=domain.id,
                   from_name="Acme", from_email="hi@m.x.com")
    db.add(a); db.flush()
    for i, (typ, cfg) in enumerate(steps):
        db.add(AutomationStep(automation_id=a.id, position=i, type=typ, config=cfg))
    db.commit(); db.refresh(a)
    return a


def test_send_wait_send_journey():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-auto"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email="a@x.com", name="A", status="subscribed"); db.add(c); db.flush()
        dom = _domain(db, ws)
        a = _automation(db, ws, dom, [
            ("send", {"subject": "Hi {name}", "html": "<p>1</p>"}),
            ("wait", {"delay_hours": 48}),
            ("send", {"subject": "Bye", "html": "<p>2</p>"}),
        ])
        run = engine.enroll(db, a, c)
        assert run is not None

        engine.advance_run(db, run)          # sends #1, hits wait -> pauses
        db.refresh(run)
        assert len(FakeSmtp.sent) == 1
        assert run.status == "active" and run.position == 2
        assert run.next_run_at > datetime.utcnow()

        run.next_run_at = datetime.utcnow() - timedelta(seconds=1)   # simulate wait elapsed
        db.commit()
        engine.advance_run(db, run)          # sends #2, ends
        db.refresh(run)
        assert len(FakeSmtp.sent) == 2
        assert run.status == "done"
        msgs = db.query(Message).filter(Message.automation_id == a.id).count()
        assert msgs == 2
    finally:
        db.close()


def test_condition_exits_non_matching():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-cond"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email="c@x.com", status="subscribed", attributes={"country": "CA"})
        db.add(c); db.flush()
        dom = _domain(db, ws)
        a = _automation(db, ws, dom, [
            ("condition", {"rules": {"all": [{"field": "attributes.country", "op": "eq", "value": "US"}]}}),
            ("send", {"subject": "x", "html": "y"}),
        ])
        run = engine.enroll(db, a, c)
        engine.advance_run(db, run)
        db.refresh(run)
        assert run.status == "exited"
        assert len(FakeSmtp.sent) == 0
    finally:
        db.close()


def test_double_enroll_is_noop():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-dup"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email="d@x.com", status="subscribed"); db.add(c); db.flush()
        dom = _domain(db, ws)
        a = _automation(db, ws, dom, [("send", {"subject": "x", "html": "y"})])
        assert engine.enroll(db, a, c) is not None
        assert engine.enroll(db, a, c) is None
        assert db.query(AutomationRun).filter(AutomationRun.automation_id == a.id).count() == 1
    finally:
        db.close()


def test_send_step_rejects_cross_tenant_template():
    from icereach.models import Template
    db = SessionLocal()
    try:
        wsa = Workspace(name="A", slug="w-a-tpl"); wsb = Workspace(name="B", slug="w-b-tpl")
        db.add_all([wsa, wsb]); db.flush()
        # template belongs to workspace B
        tpl = Template(workspace_id=wsb.id, name="B tpl", subject="secret", html="<p>secret</p>", text="secret")
        db.add(tpl); db.flush()
        c = Contact(workspace_id=wsa.id, email="a@x.com", status="subscribed"); db.add(c); db.flush()
        dom = _domain(db, wsa)
        # workspace A automation references B's template id
        a = _automation(db, wsa, dom, [("send", {"template_id": tpl.id})])
        run = engine.enroll(db, a, c)
        engine.advance_run(db, run)
        db.refresh(run)
        assert run.status == "failed"          # cross-tenant template not resolved
        assert len(FakeSmtp.sent) == 0          # nothing sent / leaked
    finally:
        db.close()


def test_advance_due_runs_processes_active():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-due"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email="e@x.com", status="subscribed"); db.add(c); db.flush()
        dom = _domain(db, ws)
        a = _automation(db, ws, dom, [("send", {"subject": "x", "html": "y"})])
        engine.enroll(db, a, c)
        n = engine.advance_due_runs(db)
        assert n == 1
        assert len(FakeSmtp.sent) == 1
    finally:
        db.close()
