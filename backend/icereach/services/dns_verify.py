"""DNS record rendering + verification for sending-domain authentication.

When an operator sets up a ``SendingDomain``, iceReach must tell them which DNS
records to publish (SPF, DKIM, DMARC) and then verify those records are live
before the domain is allowed to send. This module owns both halves:

* :func:`render_dns_records` — produce the three TXT records (with their exact
  hosts and values) the operator must publish, given the DKIM public-key TXT
  value from :func:`icereach.services.dkim.generate_keypair`.
* :func:`verify_spf` / :func:`verify_dkim` / :func:`verify_dmarc` — query DNS
  for the published TXT records and confirm each carries the expected version
  tag (``v=spf1`` / ``v=DKIM1`` / ``v=DMARC1``).

The verifiers use a process-wide ``dns.resolver.Resolver`` exposed through the
module-level :func:`get_resolver` getter so tests can monkeypatch it with a
stub that returns canned TXT answers (no real network access).
"""

from __future__ import annotations

import threading

import dns.resolver

# --------------------------------------------------------------------
# Shared DNS resolver (lazily built, thread-safe, monkeypatchable)
# --------------------------------------------------------------------
_dns_resolver: "dns.resolver.Resolver | None" = None
_dns_resolver_lock = threading.Lock()


def get_resolver() -> "dns.resolver.Resolver":
    """Return the process-wide DNS resolver, building it once (lazily, thread-safe).

    Tests monkeypatch this getter to inject a stub resolver, so all DNS access
    in this module goes through it rather than constructing a resolver inline.
    """
    global _dns_resolver
    if _dns_resolver is None:
        with _dns_resolver_lock:
            if _dns_resolver is None:
                resolver = dns.resolver.Resolver()
                resolver.nameservers = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
                resolver.timeout = 5
                resolver.lifetime = 10
                _dns_resolver = resolver
    return _dns_resolver


# --------------------------------------------------------------------
# Record rendering
# --------------------------------------------------------------------
def render_dns_records(
    domain: str,
    selector: str,
    dkim_txt_value: str,
    bounce_subdomain: str = "bounce",
) -> list[dict]:
    """Render the SPF/DKIM/DMARC TXT records the operator must publish.

    The platform sends with a ``MAIL FROM`` (envelope/Return-Path) on the
    ``{bounce_subdomain}.{domain}`` subdomain so that bounce processing is
    isolated; SPF is therefore published on that bounce subdomain, where it
    still produces SPF alignment under DMARC because the bounce subdomain is
    organizationally aligned with ``domain``.

    Args:
        domain: The verified sending domain (e.g. ``example.com``).
        selector: The DKIM selector; the public key lives at
            ``{selector}._domainkey.{domain}``.
        dkim_txt_value: The ``v=DKIM1; k=rsa; p=...`` value produced by
            :func:`icereach.services.dkim.generate_keypair`.
        bounce_subdomain: Subdomain label used for the bounce/Return-Path
            domain that carries the SPF record. Defaults to ``"bounce"``.

    Returns:
        A list of three ``{"type", "host", "value", "purpose"}`` dicts, one
        each for SPF, DKIM and DMARC.
    """
    domain = (domain or "").strip().lower().rstrip(".")
    selector = (selector or "").strip()
    bounce_subdomain = (bounce_subdomain or "").strip().lower().rstrip(".")

    return [
        {
            "type": "TXT",
            "host": f"{bounce_subdomain}.{domain}",
            "value": "v=spf1 include:_spf.icereach.dev ~all",
            "purpose": "SPF — authorizes iceReach to send for the bounce "
            "(Return-Path) subdomain; aligns under DMARC.",
        },
        {
            "type": "TXT",
            "host": f"{selector}._domainkey.{domain}",
            "value": dkim_txt_value,
            "purpose": "DKIM — public key used to verify the DKIM-Signature "
            "on outbound mail.",
        },
        {
            "type": "TXT",
            "host": f"_dmarc.{domain}",
            "value": "v=DMARC1; p=none; rua=mailto:dmarc@" + domain,
            "purpose": "DMARC — policy + aggregate-report address tying SPF "
            "and DKIM alignment together.",
        },
    ]


# --------------------------------------------------------------------
# Verification helpers
# --------------------------------------------------------------------
def _txt_strings(host: str) -> list[str]:
    """Return the decoded TXT record strings published at ``host``.

    A TXT record may be split into multiple quoted chunks; dnspython exposes
    each answer's chunks as ``.strings`` (bytes). We join the chunks of each
    answer into a single string and return one string per answer. Any DNS
    failure (no record, NXDOMAIN, timeout) yields an empty list.
    """
    host = (host or "").strip().rstrip(".")
    if not host:
        return []

    resolver = get_resolver()
    try:
        answers = resolver.resolve(host, "TXT")
    except (
        dns.resolver.NoAnswer,
        dns.resolver.NXDOMAIN,
        dns.resolver.NoNameservers,
        dns.resolver.Timeout,
    ):
        return []
    except Exception:  # noqa: BLE001 — treat any lookup error as "not present"
        return []

    results: list[str] = []
    for rdata in answers:
        chunks = getattr(rdata, "strings", None)
        if chunks is not None:
            joined = b"".join(
                c if isinstance(c, bytes) else c.encode("utf-8") for c in chunks
            )
            results.append(joined.decode("utf-8", "replace"))
        else:
            # Fall back to the record's text form (stub resolvers may yield
            # plain objects without ``.strings``).
            results.append(str(rdata).strip('"'))
    return results


def _has_txt_tag(host: str, tag: str) -> bool:
    """True if any TXT record at ``host`` contains ``tag`` (case-insensitive)."""
    needle = tag.lower()
    return any(needle in txt.lower() for txt in _txt_strings(host))


def verify_spf(domain: str, bounce_subdomain: str = "bounce") -> bool:
    """Return True if the bounce subdomain publishes an SPF (``v=spf1``) record.

    SPF is published on ``{bounce_subdomain}.{domain}`` to match the envelope
    sender used for outbound mail (see :func:`render_dns_records`).
    """
    domain = (domain or "").strip().lower().rstrip(".")
    bounce_subdomain = (bounce_subdomain or "").strip().lower().rstrip(".")
    host = f"{bounce_subdomain}.{domain}" if bounce_subdomain else domain
    return _has_txt_tag(host, "v=spf1")


def verify_dkim(domain: str, selector: str) -> bool:
    """Return True if ``{selector}._domainkey.{domain}`` publishes a DKIM key.

    A valid DKIM TXT record carries the ``v=DKIM1`` version tag.
    """
    domain = (domain or "").strip().lower().rstrip(".")
    selector = (selector or "").strip()
    return _has_txt_tag(f"{selector}._domainkey.{domain}", "v=DKIM1")


def verify_dmarc(domain: str) -> bool:
    """Return True if ``_dmarc.{domain}`` publishes a DMARC (``v=DMARC1``) policy."""
    domain = (domain or "").strip().lower().rstrip(".")
    return _has_txt_tag(f"_dmarc.{domain}", "v=DMARC1")
