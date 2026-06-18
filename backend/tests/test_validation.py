"""Tests for the email validation ladder (syntax + cached MX)."""

import pytest

from icereach.services import validation


@pytest.fixture(autouse=True)
def _clear_mx_cache():
    """Each test starts with an empty per-domain MX cache."""
    validation._mx_cache.clear()
    yield
    validation._mx_cache.clear()


# --------------------------------------------------------------------
# is_valid_syntax
# --------------------------------------------------------------------
@pytest.mark.parametrize(
    "email",
    [
        "alice@example.com",
        "first.last+tag@sub.example.co.uk",
        "user_name123@domain.io",
    ],
)
def test_is_valid_syntax_accepts(email):
    assert validation.is_valid_syntax(email) is True


@pytest.mark.parametrize(
    "email",
    [
        "nope",
        "no-at-sign.com",
        "missing@domain",          # no TLD
        "@example.com",            # no local part
        "spaces in@example.com",
        "trailing@dot.c",          # TLD too short
    ],
)
def test_is_valid_syntax_rejects(email):
    assert validation.is_valid_syntax(email) is False


# --------------------------------------------------------------------
# resolve_mx_hosts — caching
# --------------------------------------------------------------------
class _CountingResolver:
    """Stand-in resolver that records how many times resolve() is called."""

    def __init__(self, hosts):
        self._hosts = hosts
        self.calls = 0

    def resolve(self, domain, rdtype):
        self.calls += 1
        # Mimic dnspython records: objects with .preference and .exchange.
        return [
            type("R", (), {"preference": i, "exchange": f"{h}."})()
            for i, h in enumerate(self._hosts)
        ]


def test_resolve_mx_hosts_is_cached(monkeypatch):
    """A second lookup of the same domain must not hit the resolver again."""
    fake = _CountingResolver(["mx1.example.com", "mx2.example.com"])
    monkeypatch.setattr(validation, "_get_resolver", lambda: fake)

    first = validation.resolve_mx_hosts("example.com")
    second = validation.resolve_mx_hosts("example.com")

    assert first == ["mx1.example.com", "mx2.example.com"]
    assert second == first
    assert fake.calls == 1  # cache hit on the 2nd call — no extra lookup


def test_resolve_mx_hosts_caches_negatives(monkeypatch):
    """Empty (negative) results are also memoized; the resolver is hit only once."""
    fake = _CountingResolver([])
    monkeypatch.setattr(validation, "_get_resolver", lambda: fake)

    assert validation.resolve_mx_hosts("dead.example") == []
    assert validation.resolve_mx_hosts("dead.example") == []
    assert fake.calls == 1


def test_resolve_mx_hosts_blank_domain_skips_lookup(monkeypatch):
    """Blank domains short-circuit without ever building/using a resolver."""
    def _boom():  # pragma: no cover - must never be called
        raise AssertionError("resolver should not be used for blank domain")

    monkeypatch.setattr(validation, "_get_resolver", _boom)
    assert validation.resolve_mx_hosts("") == []
    assert validation.resolve_mx_hosts("   ") == []


# --------------------------------------------------------------------
# has_mx_record
# --------------------------------------------------------------------
def test_has_mx_record(monkeypatch):
    monkeypatch.setattr(validation, "resolve_mx_hosts", lambda d: ["mx.example.com"])
    assert validation.has_mx_record("example.com") is True

    monkeypatch.setattr(validation, "resolve_mx_hosts", lambda d: [])
    assert validation.has_mx_record("example.com") is False


# --------------------------------------------------------------------
# validate_email — three-state ladder
# --------------------------------------------------------------------
def test_validate_email_invalid_syntax():
    assert validation.validate_email("nope") == "Invalid syntax"


def test_validate_email_no_mx(monkeypatch):
    monkeypatch.setattr(validation, "has_mx_record", lambda d: False)
    assert validation.validate_email("alice@example.com") == "Domain not found / no MX record"


def test_validate_email_deliverable(monkeypatch):
    """With MX stubbed present, a syntactically valid address is Deliverable."""
    monkeypatch.setattr(validation, "has_mx_record", lambda d: True)
    assert validation.validate_email("alice@example.com") == "Deliverable"
