"""Re-export all models so metadata is fully populated on import."""

from .contact import Contact, ContactList, ListMembership, Segment, Suppression
from .job import AIUsage, AuditLog, Job
from .sending import (
    Campaign,
    CampaignVariant,
    Event,
    Message,
    SendingDomain,
    Template,
)
from .workspace import ApiKey, Membership, Session, User, Workspace

__all__ = [
    "Workspace", "User", "Membership", "Session", "ApiKey",
    "Contact", "ContactList", "ListMembership", "Segment", "Suppression",
    "SendingDomain", "Template", "Campaign", "CampaignVariant", "Message", "Event",
    "Job", "AuditLog", "AIUsage",
]
