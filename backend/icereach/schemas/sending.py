from typing import Any

from pydantic import BaseModel, Field


class SendingDomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""


class SendingDomainOut(BaseModel):
    id: int
    domain: str
    dkim_selector: str
    spf_verified: bool
    dkim_verified: bool
    dmarc_verified: bool
    status: str
    smtp_host: str


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
