"""Tests for the open/click tracking service."""

import pytest

from icereach.config import settings
from icereach.services import tracking


def test_token_round_trip_with_url():
    token = tracking.encode_token(42, "https://example.com/path?a=1")
    decoded = tracking.decode_token(token)
    assert decoded == {"message_id": 42, "url": "https://example.com/path?a=1"}


def test_token_round_trip_default_url_is_empty():
    token = tracking.encode_token(7)
    decoded = tracking.decode_token(token)
    assert decoded["message_id"] == 7
    assert decoded["url"] == ""


def test_tampered_token_raises_value_error():
    token = tracking.encode_token(99, "https://example.com")
    # Flip the final character to break the HMAC signature.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(ValueError):
        tracking.decode_token(tampered)


def test_garbage_token_raises_value_error():
    with pytest.raises(ValueError):
        tracking.decode_token("not-a-real-token")


def test_rewrite_html_rewrites_anchor_into_click_redirect():
    html = '<p>Hi <a href="https://example.com/buy">click</a></p>'
    out = tracking.rewrite_html(html, 123)

    prefix = f"{settings.base_url}/t/c/"
    assert prefix in out
    # The original href must no longer appear verbatim inside the anchor.
    assert 'href="https://example.com/buy"' not in out

    # The rewritten click token must decode back to the original URL + message id.
    start = out.index(prefix) + len(prefix)
    end = out.index('"', start)
    token = out[start:end]
    decoded = tracking.decode_token(token)
    assert decoded == {"message_id": 123, "url": "https://example.com/buy"}


def test_rewrite_html_injects_open_pixel():
    out = tracking.rewrite_html("<p>no links here</p>", 555)
    pixel_prefix = f"{settings.base_url}/t/o/"
    assert pixel_prefix in out
    assert ".png" in out
    assert 'width="1"' in out
    assert 'height="1"' in out

    # The pixel token decodes to the message id with no bound URL.
    start = out.index(pixel_prefix) + len(pixel_prefix)
    end = out.index(".png", start)
    token = out[start:end]
    assert tracking.decode_token(token) == {"message_id": 555, "url": ""}


def test_rewrite_html_leaves_mailto_links_untouched():
    html = '<a href="mailto:unsub@example.com">unsubscribe</a>'
    out = tracking.rewrite_html(html, 1)
    assert 'href="mailto:unsub@example.com"' in out
    assert "/t/c/" not in out


def test_is_bot_false_for_mailbox_image_proxies():
    # Gmail/Yahoo proxies fetch the pixel on a genuine human open, so they must
    # NOT be treated as bots — doing so silently dropped real opens.
    for ua in (
        "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 "
        "(via ggpht.com GoogleImageProxy)",
        "YahooMailProxy/1.0",
    ):
        assert tracking.is_bot(ua) is False


def test_is_bot_true_for_crawlers_and_preview_bots():
    for ua in ("Googlebot/2.1", "bingbot/2.0", "facebookexternalhit/1.1"):
        assert tracking.is_bot(ua) is True


def test_is_bot_false_for_normal_browser():
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    assert tracking.is_bot(ua) is False


def test_is_bot_false_for_empty_user_agent():
    assert tracking.is_bot("") is False
