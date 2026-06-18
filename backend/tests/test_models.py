import pytest
from sqlalchemy.exc import IntegrityError

from icereach.models import (
    Campaign,
    CampaignVariant,
    Contact,
    ContactList,
    ListMembership,
    Membership,
    Message,
    Suppression,
    User,
    Workspace,
)


def _workspace(db, slug="acme"):
    ws = Workspace(name="Acme", slug=slug)
    db.add(ws)
    db.flush()
    return ws


def test_identity_relationships(db):
    ws = _workspace(db)
    user = User(email="a@x.com", password_hash="h", name="A")
    db.add(user)
    db.flush()
    m = Membership(workspace_id=ws.id, user_id=user.id, role="owner")
    db.add(m)
    db.flush()
    assert m.workspace.slug == "acme"
    assert user.memberships[0].role == "owner"


def test_membership_unique(db):
    ws = _workspace(db)
    user = User(email="b@x.com", password_hash="h")
    db.add(user)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id))
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_contact_unique_per_workspace(db):
    ws = _workspace(db)
    db.add(Contact(workspace_id=ws.id, email="c@x.com"))
    db.flush()
    db.add(Contact(workspace_id=ws.id, email="c@x.com"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_same_email_different_workspaces_ok(db):
    a = _workspace(db, "a")
    b = _workspace(db, "b")
    db.add(Contact(workspace_id=a.id, email="dup@x.com"))
    db.add(Contact(workspace_id=b.id, email="dup@x.com"))
    db.flush()  # no error — uniqueness is per workspace


def test_suppression_unique(db):
    ws = _workspace(db)
    db.add(Suppression(workspace_id=ws.id, email="s@x.com", reason="unsubscribe"))
    db.flush()
    db.add(Suppression(workspace_id=ws.id, email="s@x.com", reason="hard_bounce"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_message_unique_per_campaign_contact_variant(db):
    ws = _workspace(db)
    lst = ContactList(workspace_id=ws.id, name="L")
    contact = Contact(workspace_id=ws.id, email="m@x.com")
    db.add_all([lst, contact])
    db.flush()
    camp = Campaign(workspace_id=ws.id, name="C", list_id=lst.id)
    db.add(camp)
    db.flush()
    var = CampaignVariant(campaign_id=camp.id, subject="S")
    db.add(var)
    db.flush()
    db.add(Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id, variant_id=var.id))
    db.flush()
    db.add(Message(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id, variant_id=var.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_list_membership_unique(db):
    ws = _workspace(db)
    lst = ContactList(workspace_id=ws.id, name="L")
    contact = Contact(workspace_id=ws.id, email="lm@x.com")
    db.add_all([lst, contact])
    db.flush()
    db.add(ListMembership(list_id=lst.id, contact_id=contact.id))
    db.flush()
    db.add(ListMembership(list_id=lst.id, contact_id=contact.id))
    with pytest.raises(IntegrityError):
        db.flush()
