"""Audience: Contact, ContactList, ListMembership, Segment, Suppression."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, WorkspaceScopedMixin


class Contact(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_contact_workspace_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="subscribed", nullable=False)  # subscribed|unsubscribed|cleaned
    source: Mapped[Optional[str]] = mapped_column(String(50))


class ContactList(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "contact_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))


class ListMembership(Base, TimestampMixin):
    __tablename__ = "list_memberships"
    __table_args__ = (UniqueConstraint("list_id", "contact_id", name="uq_list_contact"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("contact_lists.id", ondelete="CASCADE"), index=True, nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="subscribed", nullable=False)  # subscribed|unsubscribed|pending|cleaned
    subscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Segment(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Suppression(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_suppression_workspace_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)  # hard_bounce|complaint|unsubscribe|manual
