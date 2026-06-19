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
    # Seed one variant per template (multi-template campaigns). Combined with
    # `variants`; `template_id` is kept for backward compatibility.
    template_ids: list[int] = Field(default_factory=list)
    variants: list[VariantIn] = Field(default_factory=list)


class CampaignDuplicateIn(BaseModel):
    """Optional overrides when cloning a campaign (e.g. send to a different list)."""
    name: str | None = None
    list_id: int | None = None
    segment_id: int | None = None


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
