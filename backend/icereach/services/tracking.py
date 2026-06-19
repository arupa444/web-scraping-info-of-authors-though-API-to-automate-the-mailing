"""Open/click tracking: signed tokens, HTML rewriting, and bot filtering.

Every tracked URL carries an opaque, HMAC-signed token built with
``itsdangerous.URLSafeSerializer`` keyed by ``settings.secret_key``. The token
binds a ``message_id`` (the unit of tracking) and, for click redirects, the
original target ``url`` so the redirect endpoint can re-verify the destination
and avoid open-redirect abuse. Tampering with a token raises ``ValueError`` on
decode.

``rewrite_html`` prepares an outbound HTML body for sending: it rewrites every
``<a href>`` into a click-tracking redirect and appends a 1x1 open pixel.
``is_bot`` flags known link-preview bots and security scanners whose hits are
not human opens. Mailbox image proxies (Gmail/Yahoo) are treated as real opens.
"""

from __future__ import annotations

import re

from itsdangerous import BadSignature, URLSafeSerializer

from ..config import settings

# Salt namespaces the serializer so tracking tokens can never be confused with
# tokens minted elsewhere from the same secret_key.
_SALT = "icereach.tracking"

# Schemes that must pass through untouched: they are not http(s) navigations and
# unsubscribe links are deliberately never routed through click tracking.
_PASSTHROUGH_SCHEME = re.compile(r"^\s*(?:mailto:|tel:|#)", re.IGNORECASE)

# Match an anchor's href value (single- or double-quoted), capturing the URL.
_ANCHOR_HREF = re.compile(
    r"""(<a\b[^>]*?\bhref\s*=\s*)(["'])(.*?)\2""",
    re.IGNORECASE | re.DOTALL,
)

# Common prefetch / proxy / scanner user-agent fragments. Matched
# case-insensitively as substrings so version suffixes do not matter.
#
# NOTE: Gmail's "GoogleImageProxy" and "YahooMailProxy" are deliberately NOT in
# this list. Those proxies fetch the open pixel when a human actually opens the
# message (Gmail is the single most common client), so treating them as bots
# discarded real opens — which is exactly why a freshly-opened email reported
# zero opens. Apple Mail Privacy Protection genuinely over-counts opens, but its
# requests do not carry these proxy markers, so excluding them here does not let
# MPP back in.
_BOT_UA_FRAGMENTS: tuple[str, ...] = (
    "Googlebot",             # Google crawler
    "bingbot",               # Bing crawler
    "facebookexternalhit",   # Facebook link prefetch
    "Slackbot",              # Slack link unfurling
    "TelegramBot",           # Telegram link preview
    "Twitterbot",            # Twitter/X card fetch
    "WhatsApp",              # WhatsApp link preview
    "LinkedInBot",           # LinkedIn link preview
    "Discordbot",            # Discord link preview
    "Applebot",              # Apple crawler
    "Barracuda",             # Barracuda security scanner
    "Proofpoint",            # Proofpoint security scanner
    "Mimecast",              # Mimecast security scanner
    "Symantec",              # Symantec security scanner
    "spider",                # generic crawlers
    "crawler",
    "preview",
    "prefetch",
)

# Pre-lowercased for fast substring scanning.
_BOT_UA_LOWER: tuple[str, ...] = tuple(frag.lower() for frag in _BOT_UA_FRAGMENTS)


def _serializer() -> URLSafeSerializer:
    """Build the serializer; secret_key is read per call so test overrides apply."""
    return URLSafeSerializer(settings.secret_key, salt=_SALT)


def encode_token(message_id: int, url: str = "") -> str:
    """Sign ``message_id`` (and optional click ``url``) into an opaque token.

    Args:
        message_id: The id of the message this tracking event belongs to.
        url: Original click target to bind into the token; empty for open pixels.

    Returns:
        A URL-safe, HMAC-signed token string.
    """
    return _serializer().dumps({"message_id": message_id, "url": url})


def decode_token(token: str) -> dict:
    """Verify and decode a tracking token.

    Args:
        token: A token previously produced by :func:`encode_token`.

    Returns:
        ``{"message_id": int, "url": str}``.

    Raises:
        ValueError: If the token is tampered with, malformed, or unsigned.
    """
    try:
        payload = _serializer().loads(token)
    except BadSignature as exc:  # tampered / forged token
        raise ValueError("invalid tracking token") from exc
    except Exception as exc:  # malformed base64 / structure
        raise ValueError("invalid tracking token") from exc

    if not isinstance(payload, dict) or "message_id" not in payload:
        raise ValueError("invalid tracking token payload")

    return {"message_id": payload["message_id"], "url": payload.get("url", "")}


def _click_url(message_id: int, target: str) -> str:
    """Build the signed click-redirect URL for an original ``target`` link."""
    token = encode_token(message_id, target)
    return f"{settings.base_url}/t/c/{token}"


def _open_pixel(message_id: int) -> str:
    """Build the open-tracking pixel ``<img>`` tag for a message."""
    token = encode_token(message_id)
    src = f"{settings.base_url}/t/o/{token}.png"
    return f'<img src="{src}" width="1" height="1" alt="" />'


def rewrite_html(html: str, message_id: int) -> str:
    """Rewrite anchors for click tracking and append an open pixel.

    Every ``<a href="...">`` whose target is an http(s) navigation is rewritten
    to ``{settings.base_url}/t/c/{token}`` with the original URL signed into the
    token. ``mailto:``/``tel:``/in-page (``#``) links pass through untouched so
    that unsubscribe and protocol links are never routed through click tracking.
    A 1x1 open pixel is appended to the end of the body.

    Args:
        html: The source HTML body.
        message_id: The message id to bind into every tracking token.

    Returns:
        The rewritten HTML with the open pixel appended.
    """

    def _replace(match: re.Match[str]) -> str:
        prefix, quote, target = match.group(1), match.group(2), match.group(3)
        if not target.strip() or _PASSTHROUGH_SCHEME.match(target):
            return match.group(0)
        return f"{prefix}{quote}{_click_url(message_id, target)}{quote}"

    rewritten = _ANCHOR_HREF.sub(_replace, html)
    return rewritten + _open_pixel(message_id)


def unsubscribe_footer_html(unsub_url: str) -> str:
    """A visible "Unsubscribe" footer to append to an outbound HTML body.

    The link points at the GET ``/u/{token}`` confirmation page, which has no
    side effect — so a security scanner or link prefetcher that fetches it can
    never unsubscribe anyone; only a deliberate confirm (POST) does. Append this
    AFTER :func:`rewrite_html` so the unsubscribe link is not click-tracked.
    """
    return (
        '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;'
        "font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.5;"
        'color:#6b7280;text-align:center">'
        "Don't want these emails? "
        f'<a href="{unsub_url}" style="color:#6b7280;text-decoration:underline">Unsubscribe</a>.'
        "</div>"
    )


def unsubscribe_footer_text(unsub_url: str) -> str:
    """Plain-text counterpart of :func:`unsubscribe_footer_html`."""
    return f"\n\n--\nUnsubscribe: {unsub_url}\n"


def is_bot(user_agent: str) -> bool:
    """Return True for known prefetch/proxy/scanner user agents.

    These clients (mailbox image proxies, link-preview bots, security scanners,
    crawlers) fetch tracking pixels and links without a human in the loop, so
    their opens/clicks must be excluded from headline metrics.

    Args:
        user_agent: The raw ``User-Agent`` header value.

    Returns:
        True if the user agent matches a known bot fragment, else False.
    """
    if not user_agent:
        return False
    ua = user_agent.lower()
    return any(fragment in ua for fragment in _BOT_UA_LOWER)
