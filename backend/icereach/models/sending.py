"""Sending: SendingDomain, Template, Campaign, CampaignVariant, Message, Event."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, WorkspaceScopedMixin


class SendingDomain(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "sending_domains"
    __table_args__ = (UniqueConstraint("workspace_id", "domain", name="uq_domain_workspace"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    dkim_selector: Mapped[str] = mapped_column(String(63), default="icereach", nullable=False)
    dkim_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    dkim_public_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Transport provider: smtp (default) | resend | sendgrid (ESP HTTP APIs).
    provider: Mapped[str] = mapped_column(String(20), default="smtp", nullable=False)
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # SMTP relay used to send for this domain (Phase 1 transport).
    smtp_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_username: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    smtp_password: Mapped[str] = mapped_column(Text, default="", nullable=False)
    spf_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    dkim_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    dmarc_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|verified


class Template(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    blocks: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SavedBlock(Base, TimestampMixin, WorkspaceScopedMixin):
    """A reusable block snippet for the email builder."""

    __tablename__ = "saved_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    block: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Campaign(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|scheduled|sending|sent|failed
    sending_domain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sending_domains.id"))
    from_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    from_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    list_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contact_lists.id"))
    segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("segments.id"))
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class CampaignVariant(Base, TimestampMixin):
    __tablename__ = "campaign_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Message(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", "variant_id", name="uq_message_campaign_contact_variant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # campaign_id is null for automation-sent messages; automation_id is null for campaigns.
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    automation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True, nullable=False)
    variant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaign_variants.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)  # queued|sent|hard_bounce|soft_bounce|failed
    message_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error: Mapped[Optional[str]] = mapped_column(Text)


class Event(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # open|click|unsubscribe|bounce
    url: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64))
