from typing import Any

from pydantic import BaseModel, EmailStr, Field


class ContactIn(BaseModel):
    email: EmailStr
    name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    name: str | None = None
    attributes: dict[str, Any] | None = None
    status: str | None = None


class ContactOut(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ListOut(BaseModel):
    id: int
    name: str
    description: str | None = None


class ListAddIn(BaseModel):
    contact_ids: list[int]


class JobOut(BaseModel):
    id: int
    type: str
    status: str
    progress: int
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None
