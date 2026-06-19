"""Email provider adapter layer.

A uniform interface over transports so campaigns/automations don't care whether
delivery is raw SMTP or an ESP HTTP API. The caller renders + tracks the HTML and
computes the unsubscribe URL; the provider only delivers.
"""

from __future__ import annotations

import httpx

from .smtp import SmtpSession, build_message, dkim_sign_message


class EmailProvider:
    name = "base"

    def open(self) -> None:
        """Open any persistent connection (no-op for stateless HTTP providers)."""

    def send(self, *, from_name: str, from_email: str, to_email: str, subject: str,
             html: str, text: str, list_unsub_url: str | None = None,
             reply_to: str | None = None) -> str:
        raise NotImplementedError

    def close(self) -> None:
        """Close any persistent connection."""


class SmtpProvider(EmailProvider):
    name = "smtp"

    def __init__(self, domain):
        self.domain = domain
        self.session = SmtpSession(
            domain.smtp_host, domain.smtp_port, domain.smtp_username, domain.smtp_password,
            verify=getattr(domain, "verify_tls", True),
        )

    def open(self) -> None:
        self.session.connect()

    def send(self, *, from_name, from_email, to_email, subject, html, text, list_unsub_url=None, reply_to=None) -> str:
        extra = {"Reply-To": reply_to} if reply_to else None
        msg = build_message(from_name, from_email, to_email, subject, html, text,
                            list_unsub_url=list_unsub_url, extra_headers=extra)
        if self.domain.dkim_verified:
            wire = dkim_sign_message(msg, self.domain.domain, self.domain.dkim_selector, self.domain.dkim_private_key)
            self.session.send(from_email, to_email, wire)
        else:
            self.session.send(from_email, to_email, msg)
        return msg["Message-ID"] or ""

    def close(self) -> None:
        self.session.close()


def _unsub_headers(list_unsub_url: str | None) -> dict:
    if not list_unsub_url:
        return {}
    return {"List-Unsubscribe": f"<{list_unsub_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


class ResendProvider(EmailProvider):
    name = "resend"
    API = "https://api.resend.com/emails"

    def __init__(self, domain):
        self.api_key = domain.api_key

    def send(self, *, from_name, from_email, to_email, subject, html, text, list_unsub_url=None, reply_to=None) -> str:
        headers = _unsub_headers(list_unsub_url)
        if reply_to:
            headers["Reply-To"] = reply_to
        payload = {
            "from": f"{from_name} <{from_email}>" if from_name else from_email,
            "to": [to_email], "subject": subject, "html": html, "text": text,
            "headers": headers,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        r = httpx.post(self.API, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30)
        r.raise_for_status()
        return (r.json() or {}).get("id", "")


class SendGridProvider(EmailProvider):
    name = "sendgrid"
    API = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self, domain):
        self.api_key = domain.api_key

    def send(self, *, from_name, from_email, to_email, subject, html, text, list_unsub_url=None, reply_to=None) -> str:
        data = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": from_name or from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text or " "}, {"type": "text/html", "value": html}],
        }
        if reply_to:
            data["reply_to"] = {"email": reply_to}
        headers = _unsub_headers(list_unsub_url)
        if headers:
            data["headers"] = headers
        r = httpx.post(self.API, json=data, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30)
        r.raise_for_status()
        return r.headers.get("X-Message-Id", "")


_PROVIDERS = {"smtp": SmtpProvider, "resend": ResendProvider, "sendgrid": SendGridProvider}


def get_provider(domain) -> EmailProvider:
    cls = _PROVIDERS.get((domain.provider or "smtp").lower(), SmtpProvider)
    return cls(domain)
