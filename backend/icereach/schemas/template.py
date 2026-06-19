from typing import Any

from pydantic import BaseModel, EmailStr, Field


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class TemplateOut(BaseModel):
    id: int
    name: str
    subject: str
    blocks: list[dict[str, Any]]
    html: str
    text: str


class RenderIn(BaseModel):
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    preheader: str = ""


class RenderOut(BaseModel):
    html: str
    text: str


class TestSendIn(BaseModel):
    to_email: EmailStr
    sending_domain_id: int
    subject: str | None = None


class SavedBlockIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    block: dict[str, Any]


class SavedBlockOut(BaseModel):
    id: int
    name: str
    block: dict[str, Any]
