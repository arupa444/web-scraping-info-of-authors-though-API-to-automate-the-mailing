from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None


class WorkspaceOut(BaseModel):
    id: int
    name: str
    slug: str


class MeOut(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    role: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: str = ""


class ApiKeyOut(BaseModel):
    id: int
    name: str
    prefix: str
    scopes: str


class ApiKeyCreated(ApiKeyOut):
    token: str  # full secret, shown once
