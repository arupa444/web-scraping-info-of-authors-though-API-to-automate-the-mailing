from datetime import datetime

from icereach.db import SessionLocal
from icereach.models import Campaign, CampaignVariant, Contact, Event, Message, Workspace
from icereach.services.analytics import variant_breakdown
from icereach.services.sendtime import best_hour


def test_variant_breakdown_picks_winner():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-ab"); db.add(ws); db.flush()
        camp = Campaign(workspace_id=ws.id, name="C"); db.add(camp); db.flush()
        va = CampaignVariant(campaign_id=camp.id, subject="A"); vb = CampaignVariant(campaign_id=camp.id, subject="B")
        db.add_all([va, vb]); db.flush()
        # variant A: 2 sent, 2 opens; variant B: 2 sent, 0 opens
        for i in range(2):
            c = Contact(workspace_id=ws.id, email=f"a{i}@x.com"); db.add(c); db.flush()
            m = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=c.id, variant_id=va.id, status="sent"); db.add(m); db.flush()
            db.add(Event(workspace_id=ws.id, message_id=m.id, type="open"))
        for i in range(2):
            c = Contact(workspace_id=ws.id, email=f"b{i}@x.com"); db.add(c); db.flush()
            db.add(Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=c.id, variant_id=vb.id, status="sent"))
        db.commit()

        result = variant_breakdown(db, ws.id, camp.id)
        assert len(result["variants"]) == 2
        assert result["winner_variant_id"] == va.id
        a = next(v for v in result["variants"] if v["variant_id"] == va.id)
        assert a["open_rate"] == 1.0
    finally:
        db.close()


def test_best_hour_from_opens_else_default():
    db = SessionLocal()
    try:
        ws = Workspace(name="W", slug="w-st"); db.add(ws); db.flush()
        c = Contact(workspace_id=ws.id, email="t@x.com"); camp = Campaign(workspace_id=ws.id, name="C")
        db.add_all([c, camp]); db.flush()
        assert best_hour(db, c.id, default=9) == 9  # no history -> default
        m = Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=c.id, status="sent"); db.add(m); db.flush()
        ev = Event(workspace_id=ws.id, message_id=m.id, type="open")
        ev.created_at = datetime(2026, 1, 1, 14, 30)
        db.add(ev); db.commit()
        assert best_hour(db, c.id) == 14
    finally:
        db.close()
