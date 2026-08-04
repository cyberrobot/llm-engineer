from typing import Protocol
from uuid import UUID

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility


class AssistantNotFound(LookupError):
    pass


class DuplicateAssistantSlug(ValueError):
    pass


class AssistantConcurrentUpdate(RuntimeError):
    pass


class AssistantDeletionBlocked(RuntimeError):
    pass


class AssistantRepository(Protocol):
    def create(self, assistant: Assistant) -> Assistant: ...
    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: AssistantStatus | None = None,
        visibility: AssistantVisibility | None = None,
    ) -> tuple[list[Assistant], int]: ...
    def get_by_id(self, assistant_id: UUID) -> Assistant: ...

    def get_by_slug(self, slug: str) -> Assistant: ...
    def update(self, assistant: Assistant, *, expected_updated_at) -> Assistant: ...
    def dependency_count(self, assistant_id: UUID) -> int: ...

    def has_dependencies(self, assistant_id: UUID) -> bool: ...
    def delete(self, assistant_id: UUID) -> None: ...
