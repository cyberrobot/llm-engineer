import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

REDMOOR_ASSISTANT_SLUG = "redmoor"
REDMOOR_ASSISTANT_ID = uuid5(NAMESPACE_URL, f"assistant:{REDMOOR_ASSISTANT_SLUG}")
MAX_ASSISTANT_SLUG_LENGTH = 100
MAX_ASSISTANT_NAME_LENGTH = 255


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
        if (
            len(self.slug) > MAX_ASSISTANT_SLUG_LENGTH
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.slug) is None
        ):
            raise ValueError("Assistant slug must be a lowercase route-safe identifier.")
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("Assistant name must not be empty.")
        if len(normalized_name) > MAX_ASSISTANT_NAME_LENGTH:
            raise ValueError("Assistant name is too long.")
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized_name):
            raise ValueError("Assistant name must not contain control characters.")
        object.__setattr__(self, "name", normalized_name)
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Assistant timestamps must include a timezone.")
        if self.updated_at < self.created_at:
            raise ValueError("Assistant update timestamp cannot precede creation.")

    def rename(self, name: str, *, at: datetime) -> "Assistant":
        return replace(self, name=name, updated_at=at)

    def activate(self, *, at: datetime) -> "Assistant":
        return replace(self, status=AssistantStatus.active, updated_at=at)

    def deactivate(self, *, at: datetime) -> "Assistant":
        return replace(self, status=AssistantStatus.inactive, updated_at=at)

    def change_visibility(self, visibility: AssistantVisibility, *, at: datetime) -> "Assistant":
        return replace(self, visibility=visibility, updated_at=at)


class DocumentRetrievalState(str, Enum):
    enabled = "enabled"
    disabled = "disabled"
