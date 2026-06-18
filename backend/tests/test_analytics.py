"""Tests for the campaign analytics roll-up service."""

from icereach.models import Campaign, Contact, Event, Message, Workspace
from icereach.services import analytics


def _workspace(db, slug="acme"):
    ws = Workspace(name="Acme", slug=slug)
    db.add(ws)
    db.flush()
    return ws


def _campaign(db, ws, name="Spring"):
    camp = Campaign(workspace_id=ws.id, name=name)
    db.add(camp)
    db.flush()
    return camp


def _contact(db, ws, email):
    c = Contact(workspace_id=ws.id, email=email)
    db.add(c)
    db.flush()
    return c


def _message(db, ws, camp, contact, status="sent"):
    m = Message(
        workspace_id=ws.id,
        campaign_id=camp.id,
        contact_id=contact.id,
        status=status,
    )
    db.add(m)
    db.flush()
    return m


def _event(db, ws, message, type_, url=None):
    e = Event(workspace_id=ws.id, message_id=message.id, type=type_, url=url)
    db.add(e)
    db.flush()
    return e


def _seed_campaign(db, ws):
    """Seed a campaign with 3 sent messages, 1 hard bounce, 1 soft bounce.

    Events:
      - m1: 2 opens (duplicate) + 1 click
      - m2: 1 open + 2 clicks (duplicate) + 1 unsubscribe
      - m3: sent but no engagement
    So: sent=3, hard_bounce=1, soft_bounce=1,
        total_opens=3, unique_opens=2, total_clicks=3, unique_clicks=2,
        unsubscribes=1.
    """
    camp = _campaign(db, ws)
    m1 = _message(db, ws, camp, _contact(db, ws, "a@x.com"), status="sent")
    m2 = _message(db, ws, camp, _contact(db, ws, "b@x.com"), status="sent")
    _message(db, ws, camp, _contact(db, ws, "c@x.com"), status="sent")
    _message(db, ws, camp, _contact(db, ws, "d@x.com"), status="hard_bounce")
    _message(db, ws, camp, _contact(db, ws, "e@x.com"), status="soft_bounce")

    # m1: duplicate opens collapse to one unique; one click.
    _event(db, ws, m1, "open")
    _event(db, ws, m1, "open")
    _event(db, ws, m1, "click", url="https://example.com/buy")

    # m2: one open; duplicate clicks collapse to one unique; one unsubscribe.
    _event(db, ws, m2, "open")
    _event(db, ws, m2, "click", url="https://example.com/buy")
    _event(db, ws, m2, "click", url="https://example.com/buy")
    _event(db, ws, m2, "unsubscribe")

    db.flush()
    return camp


def test_campaign_metrics_full_rollup(db):
    ws = _workspace(db)
    camp = _seed_campaign(db, ws)

    m = analytics.campaign_metrics(db, ws.id, camp.id)

    assert m["sent"] == 3
    assert m["hard_bounce"] == 1
    assert m["soft_bounce"] == 1

    assert m["total_opens"] == 3
    assert m["unique_opens"] == 2
    assert m["total_clicks"] == 3
    assert m["unique_clicks"] == 2
    assert m["unsubscribes"] == 1

    # ctr = total_clicks / sent = 3 / 3 = 1.0
    assert m["ctr"] == 1.0
    # ctor = unique_clicks / unique_opens = 2 / 2 = 1.0
    assert m["ctor"] == 1.0

    # Phase 1: these are intentionally not yet computed.
    assert m["delivered"] is None
    assert m["complaints"] is None


def test_campaign_metrics_ctr_ctor_values(db):
    """Verify ratio arithmetic with non-trivial numbers."""
    ws = _workspace(db)
    camp = _campaign(db, ws)

    # 4 sent messages.
    msgs = [
        _message(db, ws, camp, _contact(db, ws, f"u{i}@x.com"), status="sent")
        for i in range(4)
    ]
    # 2 distinct messages opened (one duplicated -> 3 total opens).
    _event(db, ws, msgs[0], "open")
    _event(db, ws, msgs[0], "open")
    _event(db, ws, msgs[1], "open")
    # 1 distinct message clicked.
    _event(db, ws, msgs[0], "click", url="https://e.com")
    db.flush()

    m = analytics.campaign_metrics(db, ws.id, camp.id)

    assert m["sent"] == 4
    assert m["total_opens"] == 3
    assert m["unique_opens"] == 2
    assert m["unique_clicks"] == 1
    # ctr = 1 click / 4 sent
    assert m["ctr"] == 1 / 4
    # ctor = 1 unique click / 2 unique opens
    assert m["ctor"] == 1 / 2


def test_campaign_metrics_divide_by_zero_guard(db):
    """Empty campaign: no sends, no events -> ratios are 0.0, not errors."""
    ws = _workspace(db)
    camp = _campaign(db, ws)

    m = analytics.campaign_metrics(db, ws.id, camp.id)

    assert m["sent"] == 0
    assert m["total_opens"] == 0
    assert m["unique_opens"] == 0
    assert m["total_clicks"] == 0
    assert m["unique_clicks"] == 0
    assert m["unsubscribes"] == 0
    assert m["hard_bounce"] == 0
    assert m["soft_bounce"] == 0
    assert m["ctr"] == 0
    assert m["ctor"] == 0
    assert m["delivered"] is None
    assert m["complaints"] is None


def test_campaign_metrics_ctor_guard_opens_zero_clicks_present(db):
    """No opens but clicks recorded -> ctor guards to 0.0 (no ZeroDivisionError)."""
    ws = _workspace(db)
    camp = _campaign(db, ws)
    msg = _message(db, ws, camp, _contact(db, ws, "z@x.com"), status="sent")
    _event(db, ws, msg, "click", url="https://e.com")
    db.flush()

    m = analytics.campaign_metrics(db, ws.id, camp.id)

    assert m["unique_opens"] == 0
    assert m["unique_clicks"] == 1
    assert m["ctor"] == 0  # guarded
    assert m["ctr"] == 1.0  # 1 click / 1 sent


def test_campaign_metrics_is_workspace_scoped(db):
    """Another workspace's identical campaign data must not bleed in."""
    ws_a = _workspace(db, slug="a")
    ws_b = _workspace(db, slug="b")

    camp_a = _seed_campaign(db, ws_a)
    # Seed noise in workspace B that would inflate counts if not scoped.
    _seed_campaign(db, ws_b)

    m = analytics.campaign_metrics(db, ws_a.id, camp_a.id)

    # Identical to the single-workspace roll-up: B's rows are excluded.
    assert m["sent"] == 3
    assert m["hard_bounce"] == 1
    assert m["total_opens"] == 3
    assert m["unique_opens"] == 2
    assert m["unique_clicks"] == 2
    assert m["unsubscribes"] == 1


def test_campaign_metrics_is_campaign_scoped(db):
    """A second campaign in the same workspace must not contribute counts."""
    ws = _workspace(db)
    camp1 = _seed_campaign(db, ws)
    camp2 = _campaign(db, ws, name="Other")
    other_msg = _message(
        db, ws, camp2, _contact(db, ws, "other@x.com"), status="sent"
    )
    _event(db, ws, other_msg, "open")
    db.flush()

    m = analytics.campaign_metrics(db, ws.id, camp1.id)

    # camp2's sent message and open are excluded.
    assert m["sent"] == 3
    assert m["total_opens"] == 3
    assert m["unique_opens"] == 2
