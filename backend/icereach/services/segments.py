"""Segment rule engine: a small JSON DSL compiled to a SQLAlchemy filter over ``Contact``.

A rule node is one of:

* ``{"all": [node, ...]}``  -> logical AND of children
* ``{"any": [node, ...]}``  -> logical OR of children
* ``{"not": node}``         -> logical NOT of a single child
* ``{"field": ..., "op": ..., "value": ...}`` -> a leaf comparison

Fields address either a top-level ``Contact`` column (``email``, ``name``,
``status``) or a key inside the JSON ``attributes`` map via the dotted form
``attributes.<key>`` (e.g. ``attributes.country``).

Supported leaf operators:

    eq, neq, contains, gt, lt, in, exists

Anything else (an unknown operator, an unknown field, a malformed node) raises
``ValueError`` so bad segment definitions fail loudly rather than silently
matching everyone or no one.

The public surface is:

* :func:`build_filter` -- DSL -> SQLAlchemy ``ColumnElement`` (no workspace scope)
* :func:`evaluate`     -- run the filter, always AND-scoped to a workspace
* :func:`preview`      -- ``{"count": int, "sample": [email, ...]}`` for a workspace
"""

from typing import Any

from sqlalchemy import and_, not_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..models import Contact

# Top-level Contact columns that may be addressed directly by a leaf rule.
_COLUMN_FIELDS = ("email", "name", "status")

# Operators we accept on a leaf node.
_OPS = ("eq", "neq", "contains", "gt", "lt", "in", "exists")


def _coerce_number(value: Any) -> float:
    """Coerce a comparison ``value`` to a float for gt/lt, raising ValueError on failure."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"gt/lt requires a numeric value, got {value!r}") from exc


def _resolve_field(field: str) -> tuple[ColumnElement, bool]:
    """Resolve a field name to a SQLAlchemy expression.

    Returns ``(expression, is_attribute)``. For ``attributes.<key>`` the
    expression is the JSON element accessor; for a top-level column it is the
    mapped column. Raises ``ValueError`` for any other field.
    """
    if field in _COLUMN_FIELDS:
        return getattr(Contact, field), False

    if field.startswith("attributes."):
        key = field[len("attributes.") :]
        if not key:
            raise ValueError(f"Unknown field: {field!r}")
        return Contact.attributes[key], True

    raise ValueError(f"Unknown field: {field!r}")


def _build_leaf(node: dict) -> ColumnElement:
    """Compile a single leaf ``{"field", "op", "value"}`` node to a boolean expression."""
    field = node.get("field")
    op = node.get("op")
    value = node.get("value")

    if not isinstance(field, str):
        raise ValueError(f"Leaf rule missing a string 'field': {node!r}")
    if op not in _OPS:
        raise ValueError(f"Unknown op: {op!r}")

    expr, is_attribute = _resolve_field(field)

    # For JSON attributes, compare on the textual representation so that string
    # operators behave consistently across backends.
    cmp = expr.as_string() if is_attribute else expr

    if op == "exists":
        # Presence of the key / non-null column. For JSON attributes we test the
        # textual accessor (raw JSON_EXTRACT) because the bare accessor would be
        # wrapped in JSON_QUOTE, which turns a missing key into the string
        # ``'null'`` rather than SQL NULL and would match every row.
        return cmp.isnot(None)

    if op == "eq":
        return cmp == value
    if op == "neq":
        # NULL-safe-ish: a missing/NULL value should count as "not equal".
        return or_(cmp != value, cmp.is_(None))
    if op == "contains":
        return cmp.contains(str(value))
    if op == "gt":
        return _numeric(expr, is_attribute) > _coerce_number(value)
    if op == "lt":
        return _numeric(expr, is_attribute) < _coerce_number(value)
    if op == "in":
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"'in' requires a list value, got {value!r}")
        return cmp.in_([v for v in value])

    # Unreachable: op membership was validated above.
    raise ValueError(f"Unknown op: {op!r}")  # pragma: no cover


def _numeric(expr: ColumnElement, is_attribute: bool) -> ColumnElement:
    """Return a numeric-comparable expression for gt/lt."""
    if is_attribute:
        return expr.as_float()
    return expr


def build_filter(rules: dict) -> ColumnElement:
    """Compile a rule DSL node into a SQLAlchemy boolean ``ColumnElement``.

    Does not apply any workspace scoping; callers that touch the database should
    go through :func:`evaluate` / :func:`preview`, which AND in the workspace.
    """
    if not isinstance(rules, dict):
        raise ValueError(f"Rule node must be an object, got {rules!r}")

    if "all" in rules:
        children = rules["all"]
        if not isinstance(children, list):
            raise ValueError("'all' must be a list of nodes")
        # An empty AND matches everything.
        return and_(*[build_filter(c) for c in children]) if children else _true()

    if "any" in rules:
        children = rules["any"]
        if not isinstance(children, list):
            raise ValueError("'any' must be a list of nodes")
        # An empty OR matches nothing.
        return or_(*[build_filter(c) for c in children]) if children else _false()

    if "not" in rules:
        return not_(build_filter(rules["not"]))

    if "field" in rules or "op" in rules:
        return _build_leaf(rules)

    raise ValueError(f"Unrecognized rule node: {rules!r}")


def _true() -> ColumnElement:
    """A trivially-true predicate (matches every contact)."""
    return Contact.id.isnot(None)


def _false() -> ColumnElement:
    """A trivially-false predicate (matches no contact)."""
    return Contact.id.is_(None)


def evaluate(db: Session, workspace_id: int, rules: dict) -> list[Contact]:
    """Return the contacts in ``workspace_id`` that satisfy ``rules``.

    The compiled rule filter is always AND-ed with the workspace scope, so a
    segment can never leak contacts from another tenant.
    """
    predicate = build_filter(rules)
    return (
        db.query(Contact)
        .filter(Contact.workspace_id == workspace_id, predicate)
        .order_by(Contact.id)
        .all()
    )


def preview(db: Session, workspace_id: int, rules: dict) -> dict:
    """Summarize a segment: total matching ``count`` plus up to 5 sample emails."""
    contacts = evaluate(db, workspace_id, rules)
    return {
        "count": len(contacts),
        "sample": [c.email for c in contacts[:5]],
    }
