"""Email validation ladder: syntax + cached MX lookups.

Ported from the legacy single-file app (``app.py``) and preserved byte-for-byte
in behavior. The validator is a three-state ladder:

    Invalid syntax  ->  Domain not found / no MX record  ->  Deliverable

Building a resolver and doing an MX lookup per email is wasteful: a large list
usually contains the same handful of domains (gmail.com, etc.) thousands of
times. We configure one resolver once and memoize MX results per domain
(negatives included, so dead domains are not re-queried).
"""

import re
import threading
import time

import dns.resolver

# --------------------------------------------------------------------
# Shared DNS resolver + per-domain MX cache
# --------------------------------------------------------------------
_dns_resolver: "dns.resolver.Resolver | None" = None
_dns_resolver_lock = threading.Lock()
_mx_cache: dict[str, list] = {}
_mx_cache_lock = threading.Lock()

# Email syntax pattern (kept identical to the legacy implementation).
_EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def _get_resolver() -> "dns.resolver.Resolver":
    """Return the process-wide DNS resolver, building it once (lazily, thread-safe)."""
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


def resolve_mx_hosts(domain: str, max_retries: int = 3) -> list:
    """Return MX exchange hostnames (in preference order) for a domain, cached per-domain.

    Returns ``[]`` when the domain has no usable MX records. Results (including
    empty ones) are memoized for the lifetime of the process, so repeated
    lookups of the same domain do not re-query DNS.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return []

    with _mx_cache_lock:
        if domain in _mx_cache:
            return _mx_cache[domain]

    resolver = _get_resolver()
    hosts: list = []
    for attempt in range(max_retries):
        try:
            answers = resolver.resolve(domain, "MX")
            records = sorted(answers, key=lambda r: r.preference)
            hosts = [str(r.exchange).rstrip(".") for r in records]
            break
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            hosts = []  # definitive negative — no point retrying
            break
        except dns.resolver.Timeout:
            if attempt == max_retries - 1:
                hosts = []
            else:
                time.sleep(1)
        except Exception as e:  # noqa: BLE001 — log and retry/give up like the legacy code
            print(f"Error checking MX record for {domain}: {e}")
            if attempt == max_retries - 1:
                hosts = []
            else:
                time.sleep(1)

    with _mx_cache_lock:
        _mx_cache[domain] = hosts
    return hosts


def is_valid_syntax(email: str) -> bool:
    """Check if email has valid syntax."""
    return re.match(_EMAIL_PATTERN, email) is not None


def has_mx_record(domain: str) -> bool:
    """Check if domain has an MX record (cached, shared resolver with retry)."""
    return bool(resolve_mx_hosts(domain))


def validate_email(email: str) -> str:
    """Comprehensive email validation (three-state ladder).

    Returns one of:
        ``"Invalid syntax"``,
        ``"Domain not found / no MX record"``,
        ``"Deliverable"``.
    """
    if not is_valid_syntax(email):
        return "Invalid syntax"

    domain = email.split("@")[1]
    if not has_mx_record(domain):
        return "Domain not found / no MX record"

    return "Deliverable"
