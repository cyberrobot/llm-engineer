import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

REDMOOR_ASSISTANT_SLUG = "redmoor"
REDMOOR_ASSISTANT_ID = uuid5(NAMESPACE_URL, f"assistant:{REDMOOR_ASSISTANT_SLUG}")


class AssistantStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class AssistantVisibility(str, Enum):
    public = "public"
    private = "private"


@dataclass(frozen=True, slots=True)
class Assistant:
    id: UUID
    slug: str
    name: str
    status: AssistantStatus
    visibility: AssistantVisibility
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.id.int == 0:
            raise ValueError("Assistant ID must not be nil.")
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.slug) is None:
            raise ValueError("Assistant slug must be a lowercase route-safe identifier.")
        if not self.name.strip():
            raise ValueError("Assistant name must not be empty.")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Assistant timestamps must include a timezone.")
        if self.updated_at < self.created_at:
            raise ValueError("Assistant update timestamp cannot precede creation.")


class DocumentRetrievalState(str, Enum):
    enabled = "enabled"
    disabled = "disabled"
