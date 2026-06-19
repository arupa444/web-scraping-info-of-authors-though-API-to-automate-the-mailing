from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SignupFormIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    list_id: int | None = None
    sending_domain_id: int | None = None
    double_optin: bool = True
    success_message: str = "Thanks for subscribing!"
    redirect_url: str = ""


class SignupFormOut(BaseModel):
    id: int
    name: str
    list_id: int | None = None
    sending_domain_id: int | None = None
    double_optin: bool
    success_message: str
    redirect_url: str


class FormSubmitIn(BaseModel):
    email: EmailStr
    name: str = ""


class OutboundWebhookIn(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    events: str = ""
    active: bool = True


class OutboundWebhookOut(BaseModel):
    id: int
    url: str
    events: str
    active: bool


class V1ContactIn(BaseModel):
    email: EmailStr
    name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class V1EmailIn(BaseModel):
    to: EmailStr
    subject: str
    html: str
    text: str = ""
    sending_domain_id: int
    from_name: str = ""
    from_email: str | None = None
