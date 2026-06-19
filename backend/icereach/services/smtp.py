"""SMTP transport: reusable authenticated session + RFC 822 message building.

Ported from the legacy ``app.py`` :class:`SmtpSession`. Re-authenticating per
recipient is slow and more likely to trip provider rate limits, so the platform
connects/logs in once and reuses that single connection across a whole batch,
transparently reconnecting if the server drops it mid-batch.

This module also owns outbound message construction:

* :func:`build_message` — assemble a ``multipart/alternative`` (text + html)
  :class:`email.message.EmailMessage` with ``Date``, ``Message-ID`` and the
  one-click ``List-Unsubscribe`` headers RFC 8058 requires for bulk senders.
* :func:`dkim_sign_message` — DKIM-sign a built message and return the full
  signed wire bytes (signature header prepended via
  :func:`icereach.services.dkim.sign_message`).
"""

from __future__ import annotations

import smtplib
import ssl
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Mapping, Optional

from icereach.services.dkim import sign_message

class SmtpSession:
    """Holds a single authenticated SMTP connection for reuse across a batch.

    The connection is opened lazily on first send. Each send NOOP-probes the
    live connection and reconnects if it has gone stale, and any
    :class:`smtplib.SMTPServerDisconnected` raised by the actual send triggers
    one transparent reconnect + retry.
    """

    def __init__(self, server: str, port: int, username: str, password: str, verify: bool = True) -> None:
        """Configure the session; no network connection is made yet.

        Args:
            server: SMTP server hostname.
            port: SMTP server port (STARTTLS submission port, e.g. 587).
            username: Login username (usually the sender address).
            password: Login password / app password.
            verify: Verify the server's TLS certificate (default, secure). Set
                False ONLY for a self-signed/internal relay you trust.
        """
        self.server_host = server
        self.port = port
        self.username = username
        self.password = password
        self.verify = verify
        self.client: Optional[smtplib.SMTP] = None

    def _context(self) -> ssl.SSLContext:
        """Build the TLS context: full verification by default (works for every
        real provider — Gmail/Zoho/SES/Mailgun/...). Relaxed only when the
        operator explicitly opts out for a self-signed/internal relay."""
        context = ssl.create_default_context()
        if not self.verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def connect(self) -> None:
        """Open a fresh connection: connect, STARTTLS, then authenticate."""
        context = self._context()
        client = smtplib.SMTP(self.server_host, self.port, timeout=30)
        client.starttls(context=context)
        client.login(self.username, self.password)
        self.client = client

    def _ensure(self) -> smtplib.SMTP:
        """Return a live client, reconnecting if the existing one is stale."""
        if self.client is None:
            self.connect()
            return self.client
        try:
            if self.client.noop()[0] != 250:
                raise smtplib.SMTPException("NOOP failed")
        except Exception:
            try:
                self.client.close()
            except Exception:
                pass
            self.connect()
        return self.client

    def send(self, from_addr: str, to_addr: str, msg: object) -> None:
        """Send a message over the reused connection, reconnecting if dropped.

        Args:
            from_addr: SMTP envelope sender address.
            to_addr: SMTP envelope recipient address.
            msg: Either an :class:`email.message.EmailMessage` (sent via
                ``send_message``-style serialization) or a pre-serialized
                ``str``/``bytes`` wire message (e.g. DKIM-signed bytes).

        On :class:`smtplib.SMTPServerDisconnected` /
        :class:`smtplib.SMTPConnectError` it performs exactly one transparent
        reconnect and retries the send once.
        """
        payload = self._serialize(msg)
        try:
            self._ensure().sendmail(from_addr, to_addr, payload)
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
            # One transparent reconnect + retry.
            self.connect()
            self.client.sendmail(from_addr, to_addr, payload)

    # Backwards-compatible alias for the legacy method name.
    sendmail = send

    @staticmethod
    def _serialize(msg: object) -> object:
        """Coerce an EmailMessage to wire bytes; pass str/bytes through."""
        if isinstance(msg, EmailMessage):
            # CRLF line endings required on the wire (RFC 5321); the default
            # policy emits bare LF, which strict MTAs reject.
            return msg.as_bytes(policy=policy.SMTP)
        return msg

    def close(self) -> None:
        """Close the connection, preferring a graceful QUIT."""
        if self.client is not None:
            try:
                self.client.quit()
            except Exception:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = None


def build_message(
    from_name: str,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
    text: str,
    list_unsub_url: Optional[str] = None,
    extra_headers: Optional[Mapping[str, str]] = None,
) -> EmailMessage:
    """Build a ``multipart/alternative`` outbound message.

    The plain-text part is added first and the HTML part second, so conformant
    clients prefer the richer HTML rendering while text-only clients still get a
    readable body.

    Args:
        from_name: Display name for the ``From`` header.
        from_email: Sender address for the ``From`` header.
        to_email: Recipient address for the ``To`` header.
        subject: Message subject.
        html: HTML body part.
        text: Plain-text body part.
        list_unsub_url: When given, adds RFC 8058 one-click unsubscribe headers
            (``List-Unsubscribe`` and ``List-Unsubscribe-Post``).
        extra_headers: Optional additional headers to set verbatim.

    Returns:
        A fully populated :class:`email.message.EmailMessage`.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid()

    # Plain text first, HTML second -> multipart/alternative.
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    if list_unsub_url:
        msg["List-Unsubscribe"] = f"<{list_unsub_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    if extra_headers:
        for key, value in extra_headers.items():
            msg[key] = value

    return msg


def dkim_sign_message(
    msg: EmailMessage,
    domain: str,
    selector: str,
    private_key_pem: str,
) -> bytes:
    """DKIM-sign a built message and return the full signed wire bytes.

    Serializes ``msg`` to RFC 822 bytes, produces a ``DKIM-Signature`` header
    via :func:`icereach.services.dkim.sign_message`, and prepends it to the
    message so the returned bytes are ready to hand to the SMTP adapter.

    Args:
        msg: The message to sign (typically from :func:`build_message`).
        domain: Signing domain for the DKIM ``d=`` tag.
        selector: DKIM selector for the ``s=`` tag.
        private_key_pem: PEM-encoded RSA private key.

    Returns:
        The signed message as wire bytes, beginning with the
        ``DKIM-Signature:`` header.
    """
    # Sign the exact CRLF bytes that go on the wire, or the signature won't verify.
    message_bytes = msg.as_bytes(policy=policy.SMTP)
    signature = sign_message(message_bytes, domain, selector, private_key_pem)
    return signature + message_bytes
