from typing import Protocol
from uuid import UUID

from assistant.domain.assistant import Assistant


class AssistantNotFound(LookupError):
    pass


class AssistantRepository(Protocol):
    def get_by_id(self, assistant_id: UUID) -> Assistant: ...

    def get_by_slug(self, slug: str) -> Assistant: ...
