from typing import Any

from pydantic import BaseModel, Field


class SendingDomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    provider: str = "smtp"  # smtp | resend | sendgrid
    api_key: str = ""       # for ESP providers
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    verify_tls: bool = True
    # Reply-To address + reply tracking mailbox (optional).
    reply_to: str = ""
    reply_protocol: str = ""
    reply_host: str = ""
    reply_port: int = 995
    reply_username: str = ""
    reply_password: str = ""


class SendingDomainUpdate(BaseModel):
    """Partial update — only the reply-mailbox + relay credentials are editable."""
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    verify_tls: bool | None = None
    reply_to: str | None = None
    reply_protocol: str | None = None
    reply_host: str | None = None
    reply_port: int | None = None
    reply_username: str | None = None
    reply_password: str | None = None


class SendingDomainOut(BaseModel):
    id: int
    domain: str
    provider: str
    verify_tls: bool
    dkim_selector: str
    spf_verified: bool
    dkim_verified: bool
    dmarc_verified: bool
    status: str
    smtp_host: str
    # Reply settings (password intentionally never returned).
    reply_to: str = ""
    reply_protocol: str = ""
    reply_host: str = ""
    reply_port: int = 995
    reply_username: str = ""


class DnsRecordsOut(BaseModel):
    domain: SendingDomainOut
    records: list[dict[str, Any]]


class SegmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rules: dict[str, Any] = Field(default_factory=dict)


class SegmentOut(BaseModel):
    id: int
    name: str
    rules: dict[str, Any]


class PreviewOut(BaseModel):
    count: int
    sample: list[str]
