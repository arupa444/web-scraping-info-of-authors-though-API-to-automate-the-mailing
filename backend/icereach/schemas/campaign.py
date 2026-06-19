from pydantic import BaseModel, EmailStr, Field


class VariantIn(BaseModel):
    subject: str = ""
    html: str = ""
    text: str = ""
    weight: int = Field(default=1, ge=1)


class VariantOut(VariantIn):
    id: int


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    from_name: str = ""
    from_email: EmailStr | None = None
    sending_domain_id: int | None = None
    list_id: int | None = None
    segment_id: int | None = None
    template_id: int | None = None
    variants: list[VariantIn] = Field(default_factory=list)


class CampaignOut(BaseModel):
    id: int
    name: str
    status: str
    from_name: str
    from_email: str
    sending_domain_id: int | None = None
    list_id: int | None = None
    segment_id: int | None = None
    variants: list[VariantOut] = Field(default_factory=list)
