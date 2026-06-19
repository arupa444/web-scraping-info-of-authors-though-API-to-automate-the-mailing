import types

from icereach.services import esp


class _DummyDomain:
    def __init__(self, provider, api_key="k"):
        self.provider = provider
        self.api_key = api_key
        self.domain = "m.x.com"
        self.dkim_selector = "s"
        self.dkim_private_key = "p"
        self.dkim_verified = False
        self.smtp_host = "smtp.x.com"
        self.smtp_port = 587
        self.smtp_username = "u"
        self.smtp_password = "pw"


def _fake_response(json_data=None, headers=None):
    return types.SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: (json_data or {}),
        headers=headers or {},
    )


def test_get_provider_selects_class():
    assert isinstance(esp.get_provider(_DummyDomain("smtp")), esp.SmtpProvider)
    assert isinstance(esp.get_provider(_DummyDomain("resend")), esp.ResendProvider)
    assert isinstance(esp.get_provider(_DummyDomain("sendgrid")), esp.SendGridProvider)
    # unknown -> smtp fallback
    assert isinstance(esp.get_provider(_DummyDomain("bogus")), esp.SmtpProvider)


def test_resend_posts_and_returns_id(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["auth"] = headers.get("Authorization")
        return _fake_response(json_data={"id": "resend-123"})

    monkeypatch.setattr(esp.httpx, "post", fake_post)
    p = esp.get_provider(_DummyDomain("resend", "rk"))
    mid = p.send(from_name="Acme", from_email="a@m.x.com", to_email="b@y.com",
                 subject="Hi", html="<p>x</p>", text="x", list_unsub_url="https://u/1")
    assert mid == "resend-123"
    assert captured["url"] == esp.ResendProvider.API
    assert captured["auth"] == "Bearer rk"
    assert captured["json"]["to"] == ["b@y.com"]
    assert "List-Unsubscribe" in captured["json"]["headers"]


def test_sendgrid_returns_header_message_id(monkeypatch):
    monkeypatch.setattr(esp.httpx, "post", lambda *a, **k: _fake_response(headers={"X-Message-Id": "sg-9"}))
    p = esp.get_provider(_DummyDomain("sendgrid"))
    mid = p.send(from_name="Acme", from_email="a@m.x.com", to_email="b@y.com",
                 subject="Hi", html="<p>x</p>", text="x")
    assert mid == "sg-9"
