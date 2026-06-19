"""Growth & integrations: SignupForm (with double opt-in), OutboundWebhook."""

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, WorkspaceScopedMixin


class SignupForm(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "signup_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    list_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contact_lists.id"))
    sending_domain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sending_domains.id"))
    double_optin: Mapped[bool] = mapped_column(default=True, nullable=False)
    success_message: Mapped[str] = mapped_column(Text, default="Thanks for subscribing!", nullable=False)
    redirect_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class OutboundWebhook(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "outbound_webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    events: Mapped[str] = mapped_column(String(500), default="", nullable=False)  # csv of event names
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
