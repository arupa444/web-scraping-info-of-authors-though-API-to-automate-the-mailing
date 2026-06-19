from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class AuditLogOut(BaseModel):
    id: int
    action: str
    target: str | None = None
    user_id: int | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemberOut(BaseModel):
    user_id: int
    email: EmailStr
    name: str | None = None
    role: str


class MemberInviteIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: str = "member"


class RoleUpdateIn(BaseModel):
    role: str


class PlanOut(BaseModel):
    key: str
    name: str
    monthly_send_limit: int
    price_usd: int


class CheckoutIn(BaseModel):
    plan: str


class BillingOut(BaseModel):
    plan: str
    monthly_send_limit: int
    sent_this_month: int
