from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StepIn(BaseModel):
    type: str  # send|wait|condition
    config: dict[str, Any] = Field(default_factory=dict)


class StepOut(BaseModel):
    id: int
    position: int
    type: str
    config: dict[str, Any]


class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    trigger_type: str = "manual"  # list_subscribe|manual
    trigger_list_id: int | None = None
    sending_domain_id: int | None = None
    from_name: str = ""
    from_email: str = ""
    steps: list[StepIn] = Field(default_factory=list)


class AutomationOut(BaseModel):
    id: int
    name: str
    status: str
    trigger_type: str
    trigger_list_id: int | None = None
    sending_domain_id: int | None = None
    from_name: str
    from_email: str
    steps: list[StepOut] = Field(default_factory=list)


class EnrollIn(BaseModel):
    contact_ids: list[int] = Field(default_factory=list)
    segment_id: int | None = None


class RunOut(BaseModel):
    id: int
    contact_id: int
    position: int
    status: str
    next_run_at: datetime
    last_error: str | None = None


class SequenceIn(BaseModel):
    goal: str = Field(min_length=1)
    steps: int = Field(default=3, ge=1, le=8)
