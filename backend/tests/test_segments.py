"""Tests for icereach.services.segments (JSON rule DSL -> SQLAlchemy filter)."""

import pytest

from icereach.models import Contact, Workspace
from icereach.services.segments import build_filter, evaluate, preview


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------
def _workspace(db, slug="acme"):
    ws = Workspace(name="Acme", slug=slug)
    db.add(ws)
    db.flush()
    return ws


def _seed(db, workspace_id):
    """Seed a small, varied set of contacts; returns them keyed by email."""
    contacts = [
        Contact(
            workspace_id=workspace_id,
            email="alice@example.com",
            name="Alice",
            status="subscribed",
            attributes={"country": "US", "age": 30, "plan": "pro"},
        ),
        Contact(
            workspace_id=workspace_id,
            email="bob@example.com",
            name="Bob",
            status="subscribed",
            attributes={"country": "CA", "age": 45},
        ),
        Contact(
            workspace_id=workspace_id,
            email="carol@other.com",
            name="Carol",
            status="unsubscribed",
            attributes={"country": "US", "age": 22},
        ),
        Contact(
            workspace_id=workspace_id,
            email="dave@example.com",
            name="Dave",
            status="cleaned",
            attributes={},  # no country / age
        ),
    ]
    db.add_all(contacts)
    db.flush()
    return {c.email: c for c in contacts}


def _emails(contacts):
    return {c.email for c in contacts}


# --------------------------------------------------------------------------
# Leaf operators on top-level columns
# --------------------------------------------------------------------------
def test_eq_on_column(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "status", "op": "eq", "value": "subscribed"})
    assert _emails(out) == {"alice@example.com", "bob@example.com"}


def test_neq_on_column(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "status", "op": "neq", "value": "subscribed"})
    assert _emails(out) == {"carol@other.com", "dave@example.com"}


def test_contains_on_column(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "email", "op": "contains", "value": "@example.com"})
    assert _emails(out) == {"alice@example.com", "bob@example.com", "dave@example.com"}


def test_in_on_column(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(
        db, ws.id, {"field": "status", "op": "in", "value": ["unsubscribed", "cleaned"]}
    )
    assert _emails(out) == {"carol@other.com", "dave@example.com"}


def test_exists_on_nullable_column(db):
    ws = _workspace(db)
    extra = Contact(workspace_id=ws.id, email="noname@example.com", name=None, attributes={})
    _seed(db, ws.id)
    db.add(extra)
    db.flush()
    out = evaluate(db, ws.id, {"field": "name", "op": "exists"})
    assert "noname@example.com" not in _emails(out)
    assert "alice@example.com" in _emails(out)


# --------------------------------------------------------------------------
# Leaf operators on JSON attributes
# --------------------------------------------------------------------------
def test_eq_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.country", "op": "eq", "value": "US"})
    assert _emails(out) == {"alice@example.com", "carol@other.com"}


def test_gt_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.age", "op": "gt", "value": 25})
    assert _emails(out) == {"alice@example.com", "bob@example.com"}


def test_lt_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.age", "op": "lt", "value": 25})
    assert _emails(out) == {"carol@other.com"}


def test_exists_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.country", "op": "exists"})
    # dave has no 'country' key.
    assert _emails(out) == {"alice@example.com", "bob@example.com", "carol@other.com"}


def test_in_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.country", "op": "in", "value": ["CA", "MX"]})
    assert _emails(out) == {"bob@example.com"}


def test_contains_on_attribute(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    out = evaluate(db, ws.id, {"field": "attributes.plan", "op": "contains", "value": "pr"})
    assert _emails(out) == {"alice@example.com"}


# --------------------------------------------------------------------------
# Boolean combinators
# --------------------------------------------------------------------------
def test_all_combinator(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    rules = {
        "all": [
            {"field": "status", "op": "eq", "value": "subscribed"},
            {"field": "attributes.country", "op": "eq", "value": "US"},
        ]
    }
    out = evaluate(db, ws.id, rules)
    assert _emails(out) == {"alice@example.com"}


def test_any_combinator(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    rules = {
        "any": [
            {"field": "status", "op": "eq", "value": "cleaned"},
            {"field": "attributes.country", "op": "eq", "value": "CA"},
        ]
    }
    out = evaluate(db, ws.id, rules)
    assert _emails(out) == {"bob@example.com", "dave@example.com"}


def test_not_combinator(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    rules = {"not": {"field": "attributes.country", "op": "eq", "value": "US"}}
    out = evaluate(db, ws.id, rules)
    # bob (CA) matches; dave (no country) -> attribute is NULL, NOT(NULL=...) is
    # not TRUE, so dave is excluded — consistent with SQL three-valued logic.
    assert "bob@example.com" in _emails(out)
    assert "alice@example.com" not in _emails(out)
    assert "carol@other.com" not in _emails(out)


def test_nested_combinators(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    rules = {
        "all": [
            {"any": [
                {"field": "attributes.country", "op": "eq", "value": "US"},
                {"field": "attributes.country", "op": "eq", "value": "CA"},
            ]},
            {"not": {"field": "status", "op": "eq", "value": "unsubscribed"}},
        ]
    }
    out = evaluate(db, ws.id, rules)
    # US or CA, and not unsubscribed -> alice (US/subscribed), bob (CA/subscribed).
    # carol is US but unsubscribed -> excluded.
    assert _emails(out) == {"alice@example.com", "bob@example.com"}


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------
def test_unknown_op_raises(db):
    with pytest.raises(ValueError):
        build_filter({"field": "status", "op": "startswith", "value": "x"})


def test_unknown_field_raises(db):
    with pytest.raises(ValueError):
        build_filter({"field": "phone", "op": "eq", "value": "x"})


def test_unknown_field_attributes_empty_key_raises(db):
    with pytest.raises(ValueError):
        build_filter({"field": "attributes.", "op": "eq", "value": "x"})


def test_in_with_non_list_raises(db):
    with pytest.raises(ValueError):
        build_filter({"field": "status", "op": "in", "value": "subscribed"})


def test_malformed_node_raises(db):
    with pytest.raises(ValueError):
        build_filter({"foo": "bar"})


def test_build_filter_rejects_non_dict(db):
    with pytest.raises(ValueError):
        build_filter("not-a-dict")


# --------------------------------------------------------------------------
# Workspace scoping
# --------------------------------------------------------------------------
def test_evaluate_is_workspace_scoped(db):
    ws_a = _workspace(db, "a")
    ws_b = _workspace(db, "b")
    db.add(Contact(workspace_id=ws_a.id, email="shared@x.com", status="subscribed", attributes={}))
    db.add(Contact(workspace_id=ws_b.id, email="shared@x.com", status="subscribed", attributes={}))
    db.flush()

    rules = {"field": "status", "op": "eq", "value": "subscribed"}
    out_a = evaluate(db, ws_a.id, rules)
    out_b = evaluate(db, ws_b.id, rules)

    assert {c.workspace_id for c in out_a} == {ws_a.id}
    assert {c.workspace_id for c in out_b} == {ws_b.id}
    assert len(out_a) == 1 and len(out_b) == 1


# --------------------------------------------------------------------------
# preview
# --------------------------------------------------------------------------
def test_preview_counts_and_samples(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    result = preview(db, ws.id, {"field": "status", "op": "eq", "value": "subscribed"})
    assert result["count"] == 2
    assert set(result["sample"]) == {"alice@example.com", "bob@example.com"}


def test_preview_sample_capped_at_five(db):
    ws = _workspace(db)
    for i in range(8):
        db.add(Contact(workspace_id=ws.id, email=f"u{i}@x.com", status="subscribed", attributes={}))
    db.flush()
    result = preview(db, ws.id, {"field": "status", "op": "eq", "value": "subscribed"})
    assert result["count"] == 8
    assert len(result["sample"]) == 5


def test_preview_empty_match(db):
    ws = _workspace(db)
    _seed(db, ws.id)
    result = preview(db, ws.id, {"field": "status", "op": "eq", "value": "nonexistent"})
    assert result == {"count": 0, "sample": []}
