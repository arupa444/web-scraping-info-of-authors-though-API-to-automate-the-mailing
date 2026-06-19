"""Tests for the SMTP transport service (icereach.services.smtp).

No network is touched: ``smtplib.SMTP`` is replaced with a fake recording
class that captures connect/login/sendmail calls and can simulate a dropped
connection.
"""

import smtplib

import pytest

from icereach.services import smtp as smtp_mod
from icereach.services.dkim import generate_keypair
from icereach.services.smtp import SmtpSession, build_message, dkim_sign_message


class FakeSMTP:
    """Recording stand-in for ``smtplib.SMTP`` (no network).

    Every instance registers itself on the class-level ``instances`` list so a
    test can inspect how many connections were opened. ``fail_noop_once`` makes
    the next ``noop`` raise to simulate a server-dropped connection, and
    ``fail_send_disconnect_once`` makes the next ``sendmail`` raise
    :class:`smtplib.SMTPServerDisconnected`.
    """

    instances: list["FakeSMTP"] = []
    # Test-controlled fault injection (consumed once each).
    fail_noop_once = False
    fail_send_disconnect_once = False

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False
        self.sent = []
        self.closed = False
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.started_tls = True
        self.tls_context = context
        return (220, b"ready")

    def login(self, username, password):
        self.logged_in = True
        self.username = username
        self.password = password
        return (235, b"ok")

    def noop(self):
        if FakeSMTP.fail_noop_once:
            FakeSMTP.fail_noop_once = False
            raise smtplib.SMTPServerDisconnected("simulated stale connection")
        return (250, b"ok")

    def sendmail(self, from_addr, to_addr, payload):
        if FakeSMTP.fail_send_disconnect_once:
            FakeSMTP.fail_send_disconnect_once = False
            raise smtplib.SMTPServerDisconnected("simulated mid-send disconnect")
        self.sent.append((from_addr, to_addr, payload))
        return {}

    def quit(self):
        self.quit_called = True

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _patch_smtp(monkeypatch):
    """Replace smtplib.SMTP with the recording fake for every test."""
    FakeSMTP.instances = []
    FakeSMTP.fail_noop_once = False
    FakeSMTP.fail_send_disconnect_once = False
    monkeypatch.setattr(smtp_mod.smtplib, "SMTP", FakeSMTP)
    yield


def _session():
    return SmtpSession("smtp.example.com", 587, "user@example.com", "secret")


def test_send_reuses_single_connection_across_two_sends():
    """Two sends over a healthy session open exactly one connection."""
    session = _session()
    session.send("user@example.com", "a@example.org", "msg-a")
    session.send("user@example.com", "b@example.org", "msg-b")

    # Only one underlying SMTP connection was created.
    assert len(FakeSMTP.instances) == 1
    conn = FakeSMTP.instances[0]
    assert conn.started_tls is True
    assert conn.logged_in is True
    # Both messages went out on that one connection.
    assert [s[1] for s in conn.sent] == ["a@example.org", "b@example.org"]


def test_send_reconnects_after_simulated_disconnect():
    """A dropped connection mid-batch triggers a transparent reconnect."""
    session = _session()
    session.send("user@example.com", "a@example.org", "msg-a")
    assert len(FakeSMTP.instances) == 1

    # Simulate the server dropping the connection: the next send's sendmail
    # raises SMTPServerDisconnected, which must reconnect + retry.
    FakeSMTP.fail_send_disconnect_once = True
    session.send("user@example.com", "b@example.org", "msg-b")

    # A second connection was opened to carry the retried message.
    assert len(FakeSMTP.instances) == 2
    new_conn = FakeSMTP.instances[1]
    assert new_conn.started_tls is True
    assert new_conn.logged_in is True
    assert new_conn.sent[-1][1] == "b@example.org"


def test_send_reconnects_when_noop_probe_fails():
    """A stale connection detected via NOOP is replaced before sending."""
    session = _session()
    session.send("user@example.com", "a@example.org", "msg-a")
    assert len(FakeSMTP.instances) == 1

    FakeSMTP.fail_noop_once = True
    session.send("user@example.com", "b@example.org", "msg-b")

    assert len(FakeSMTP.instances) == 2
    assert FakeSMTP.instances[1].sent[-1][1] == "b@example.org"


def test_tls_verified_by_default_for_any_host():
    """Verification is on by default for every host (Gmail, Zoho, SES, custom...)."""
    import ssl as _ssl
    for host in ("smtp.gmail.com", "smtp.zoho.in", "smtp.example.com", "mail.internal.corp"):
        ctx = SmtpSession(host, 587, "u", "p")._context()
        assert ctx.check_hostname is True
        assert ctx.verify_mode == _ssl.CERT_REQUIRED


def test_tls_relaxed_only_when_opted_out():
    """verify=False (trusted self-signed/internal relay) relaxes verification."""
    import ssl as _ssl
    ctx = SmtpSession("mail.internal.corp", 587, "u", "p", verify=False)._context()
    assert ctx.check_hostname is False
    assert ctx.verify_mode == _ssl.CERT_NONE


def test_build_message_is_multipart_with_both_parts():
    """build_message yields multipart/alternative with text + html parts."""
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi there</p>",
        text="Hi there",
    )

    assert msg.is_multipart()
    assert msg.get_content_type() == "multipart/alternative"

    subtypes = [part.get_content_type() for part in msg.iter_parts()]
    assert "text/plain" in subtypes
    assert "text/html" in subtypes

    # Required transport headers are present.
    assert msg["Date"]
    assert msg["Message-ID"]
    assert msg["Subject"] == "Hello"
    assert "sender@example.com" in msg["From"]

    # Body content survives in both parts.
    bodies = {
        part.get_content_type(): part.get_content().strip()
        for part in msg.iter_parts()
    }
    assert bodies["text/plain"] == "Hi there"
    assert "<p>Hi there</p>" in bodies["text/html"]


def test_build_message_without_unsub_omits_list_headers():
    """Without a List-Unsubscribe URL, no list headers are added."""
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
    )
    assert "List-Unsubscribe" not in msg
    assert "List-Unsubscribe-Post" not in msg


def test_build_message_adds_one_click_unsubscribe_headers():
    """A List-Unsubscribe URL adds the RFC 8058 one-click headers."""
    url = "https://app.example.com/u/abc123"
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
        list_unsub_url=url,
    )

    assert msg["List-Unsubscribe"] == f"<{url}>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_build_message_sets_extra_headers():
    """extra_headers are set verbatim on the message."""
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
        extra_headers={"X-Campaign-ID": "camp-42"},
    )
    assert msg["X-Campaign-ID"] == "camp-42"


def test_dkim_sign_message_returns_signed_wire_bytes():
    """dkim_sign_message prepends a DKIM-Signature header to the wire bytes."""
    private_pem, _ = generate_keypair()
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
    )

    signed = dkim_sign_message(
        msg,
        domain="example.com",
        selector="ir1",
        private_key_pem=private_pem,
    )

    assert isinstance(signed, bytes)
    assert b"DKIM-Signature:" in signed
    # The signature header is prepended ahead of the original message headers.
    assert signed.index(b"DKIM-Signature:") < signed.index(b"Subject:")
    assert b"d=example.com" in signed
    assert b"s=ir1" in signed


def test_send_accepts_email_message_object():
    """send serializes an EmailMessage to bytes before handing to sendmail."""
    session = _session()
    msg = build_message(
        from_name="Sender",
        from_email="sender@example.com",
        to_email="rcpt@example.org",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
    )
    session.send("sender@example.com", "rcpt@example.org", msg)

    conn = FakeSMTP.instances[0]
    sent_payload = conn.sent[0][2]
    assert isinstance(sent_payload, bytes)
    assert b"Subject: Hello" in sent_payload
