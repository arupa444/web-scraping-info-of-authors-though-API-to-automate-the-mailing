from pydantic import BaseModel, Field


class SubjectsIn(BaseModel):
    brief: str = Field(min_length=1)
    n: int = Field(default=5, ge=1, le=10)
    tone: str = "professional"


class BodyIn(BaseModel):
    brief: str = Field(min_length=1)
    tone: str = "professional"


class CritiqueIn(BaseModel):
    subject: str = ""
    html: str = ""
