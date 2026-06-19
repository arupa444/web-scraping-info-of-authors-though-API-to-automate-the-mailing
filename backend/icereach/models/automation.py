"""Automation journeys: Automation, AutomationStep, AutomationRun."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .base import TimestampMixin, WorkspaceScopedMixin


class Automation(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|active|paused
    trigger_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)  # list_subscribe|manual
    trigger_list_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contact_lists.id"))
    sending_domain_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sending_domains.id"))
    from_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    from_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)


class AutomationStep(Base, TimestampMixin):
    __tablename__ = "automation_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # send|wait|condition
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AutomationRun(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True, nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|done|exited|failed
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
