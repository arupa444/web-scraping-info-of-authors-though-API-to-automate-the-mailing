"""Tests for DNS record rendering + SPF/DKIM/DMARC verification.

These tests never touch the network: they monkeypatch the module-level
``get_resolver`` getter with a stub resolver that returns canned TXT answers
keyed by hostname, mimicking dnspython's record shape (``.strings`` chunks).
"""

import dns.resolver
import pytest

from icereach.services import dns_verify


# --------------------------------------------------------------------
# Stub resolver mimicking dnspython's TXT answer shape
# --------------------------------------------------------------------
class _FakeTxtRecord:
    """Mimic a dnspython TXT rdata: ``.strings`` is a list of byte chunks."""

    def __init__(self, value: str):
        # TXT values can be split into <=255-byte chunks; we keep it whole.
        self.strings = [value.encode("utf-8")]

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return '"' + b"".join(self.strings).decode("utf-8") + '"'


class _FakeResolver:
    """Return canned TXT records per host; raise NXDOMAIN for unknown hosts."""

    def __init__(self, records: dict[str, list[str]]):
        # Normalize keys to bare hostnames (no trailing dot).
        self._records = {k.rstrip("."): v for k, v in records.items()}

    def resolve(self, host, rdtype):
        assert rdtype == "TXT"
        key = str(host).rstrip(".")
        if key not in self._records:
            raise dns.resolver.NXDOMAIN(f"no record for {key}")
        return [_FakeTxtRecord(v) for v in self._records[key]]


@pytest.fixture
def patch_resolver(monkeypatch):
    """Install a stub resolver built from a {host: [txt, ...]} mapping."""

    def _install(records: dict[str, list[str]]):
        fake = _FakeResolver(records)
        monkeypatch.setattr(dns_verify, "get_resolver", lambda: fake)
        return fake

    return _install


# --------------------------------------------------------------------
# render_dns_records
# --------------------------------------------------------------------
def test_render_dns_records_hosts_and_types():
    """The three records have the correct hosts, all TXT, with a DKIM value."""
    dkim_value = "v=DKIM1; k=rsa; p=AAAB"
    records = dns_verify.render_dns_records("Example.com", "ice2024", dkim_value)

    assert len(records) == 3
    assert all(r["type"] == "TXT" for r in records)
    assert all(set(r) == {"type", "host", "value", "purpose"} for r in records)

    by_host = {r["host"]: r for r in records}
    # SPF lives on the bounce subdomain (default 'bounce'); domain lowercased.
    assert "bounce.example.com" in by_host
    assert by_host["bounce.example.com"]["value"].startswith("v=spf1")
    # DKIM at {selector}._domainkey.{domain}, carrying the provided value.
    assert "ice2024._domainkey.example.com" in by_host
    assert by_host["ice2024._domainkey.example.com"]["value"] == dkim_value
    # DMARC at _dmarc.{domain}.
    assert "_dmarc.example.com" in by_host
    assert by_host["_dmarc.example.com"]["value"].startswith("v=DMARC1")


def test_render_dns_records_custom_bounce_subdomain():
    records = dns_verify.render_dns_records(
        "example.com", "sel", "v=DKIM1; p=x", bounce_subdomain="mail"
    )
    hosts = {r["host"] for r in records}
    assert "mail.example.com" in hosts
    # SPF record is the one on the bounce subdomain.
    spf = next(r for r in records if r["host"] == "mail.example.com")
    assert "v=spf1" in spf["value"]


# --------------------------------------------------------------------
# verify_spf
# --------------------------------------------------------------------
def test_verify_spf_true(patch_resolver):
    patch_resolver({"bounce.example.com": ["v=spf1 include:_spf.icereach.dev ~all"]})
    assert dns_verify.verify_spf("example.com") is True


def test_verify_spf_false_wrong_record(patch_resolver):
    patch_resolver({"bounce.example.com": ["some-unrelated-verification-token"]})
    assert dns_verify.verify_spf("example.com") is False


def test_verify_spf_false_missing(patch_resolver):
    patch_resolver({})  # NXDOMAIN for everything
    assert dns_verify.verify_spf("example.com") is False


def test_verify_spf_custom_bounce_subdomain(patch_resolver):
    patch_resolver({"mail.example.com": ["v=spf1 -all"]})
    assert dns_verify.verify_spf("example.com", bounce_subdomain="mail") is True
    # Default bounce host has no record -> False.
    assert dns_verify.verify_spf("example.com") is False


# --------------------------------------------------------------------
# verify_dkim
# --------------------------------------------------------------------
def test_verify_dkim_true(patch_resolver):
    patch_resolver({"sel._domainkey.example.com": ["v=DKIM1; k=rsa; p=ABCD"]})
    assert dns_verify.verify_dkim("example.com", "sel") is True


def test_verify_dkim_false_wrong_selector(patch_resolver):
    patch_resolver({"sel._domainkey.example.com": ["v=DKIM1; k=rsa; p=ABCD"]})
    # A different selector has no published key.
    assert dns_verify.verify_dkim("example.com", "other") is False


def test_verify_dkim_false_missing(patch_resolver):
    patch_resolver({})
    assert dns_verify.verify_dkim("example.com", "sel") is False


# --------------------------------------------------------------------
# verify_dmarc
# --------------------------------------------------------------------
def test_verify_dmarc_true(patch_resolver):
    patch_resolver({"_dmarc.example.com": ["v=DMARC1; p=reject; rua=mailto:d@example.com"]})
    assert dns_verify.verify_dmarc("example.com") is True


def test_verify_dmarc_false_wrong_record(patch_resolver):
    patch_resolver({"_dmarc.example.com": ["v=spf1 ~all"]})  # wrong tag
    assert dns_verify.verify_dmarc("example.com") is False


def test_verify_dmarc_false_missing(patch_resolver):
    patch_resolver({})
    assert dns_verify.verify_dmarc("example.com") is False


# --------------------------------------------------------------------
# Multi-chunk TXT + case-insensitivity
# --------------------------------------------------------------------
def test_verify_handles_multi_chunk_txt(monkeypatch):
    """TXT records split across multiple chunks are joined before matching."""

    class _MultiChunk:
        strings = [b"v=DK", b"IM1; k=rsa; p=ABCD"]

    class _R:
        def resolve(self, host, rdtype):
            return [_MultiChunk()]

    monkeypatch.setattr(dns_verify, "get_resolver", lambda: _R())
    assert dns_verify.verify_dkim("example.com", "sel") is True


def test_verify_tag_match_is_case_insensitive(patch_resolver):
    patch_resolver({"_dmarc.example.com": ["V=DMARC1; p=none"]})
    assert dns_verify.verify_dmarc("example.com") is True
