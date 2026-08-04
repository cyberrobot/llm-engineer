import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from assistant.domain.assistant import (
    REDMOOR_ASSISTANT_ID,
    Assistant,
    AssistantStatus,
    AssistantVisibility,
)
from assistant.domain.assistant_repository import AssistantDeletionBlocked, AssistantRepository
from core.metrics import assistant_administration_metrics

logger = logging.getLogger(__name__)


class EmptyAssistantUpdate(ValueError):
    pass


class ProtectedAssistantDeletion(AssistantDeletionBlocked):
    pass


@dataclass(frozen=True, slots=True)
class AssistantView:
    assistant: Assistant
    knowledge_source_count: int
    has_dependencies: bool

    @property
    def deletion_allowed(self):
        return self.assistant.id != REDMOOR_ASSISTANT_ID and not self.has_dependencies


class AssistantAdministrationService:
    def __init__(
        self,
        repository: AssistantRepository,
        *,
        clock=lambda: datetime.now(timezone.utc),
        id_factory=uuid4,
    ):
        self.repository, self.clock, self.id_factory = repository, clock, id_factory

    def list_assistants(self, *, limit, offset, status=None, visibility=None):
        return self.repository.list(
            limit=limit, offset=offset, status=status, visibility=visibility
        )

    def get_assistant(self, assistant_id: UUID):
        assistant = self.repository.get_by_id(assistant_id)
        return AssistantView(
            assistant,
            self.repository.dependency_count(assistant_id),
            self.repository.has_dependencies(assistant_id),
        )

    def create_assistant(
        self, *, slug, name, status=AssistantStatus.inactive, visibility=AssistantVisibility.private
    ):
        now = self.clock()
        assistant = Assistant(self.id_factory(), slug, name, status, visibility, now, now)
        try:
            result = self.repository.create(assistant)
        except Exception:
            self._metric("conflicts")
            raise
        self._metric("created")
        self._log("assistant_created", result)
        return result

    def update_assistant(
        self, assistant_id, *, concurrency_token, name=None, status=None, visibility=None
    ):
        if name is None and status is None and visibility is None:
            raise EmptyAssistantUpdate("At least one mutable field is required.")
        current = self.repository.get_by_id(assistant_id)
        updated = current
        now = max(self.clock(), current.updated_at + timedelta(microseconds=1))
        if name is not None:
            updated = updated.rename(name, at=now)
        if status is not None:
            updated = (
                updated.activate(at=now)
                if status is AssistantStatus.active
                else updated.deactivate(at=now)
            )
        if visibility is not None:
            updated = updated.change_visibility(visibility, at=now)
        try:
            result = self.repository.update(updated, expected_updated_at=concurrency_token)
        except Exception:
            self._metric("conflicts")
            raise
        self._metric("updated")
        self._log("assistant_updated", result)
        if current.status is not result.status:
            self._log(
                "assistant_activated"
                if result.status is AssistantStatus.active
                else "assistant_deactivated",
                result,
            )
        if current.visibility is not result.visibility:
            self._log("assistant_visibility_changed", result)
        return result

    def delete_assistant(self, assistant_id):
        if assistant_id == REDMOOR_ASSISTANT_ID:
            raise ProtectedAssistantDeletion("The seeded assistant cannot be deleted.")
        try:
            self.repository.delete(assistant_id)
        except AssistantDeletionBlocked:
            self._metric("conflicts")
            raise
        self._metric("deleted")
        try:
            logger.info("assistant_deleted", extra={"assistant_id": str(assistant_id)})
        except Exception:
            pass

    def _metric(self, name):
        try:
            getattr(assistant_administration_metrics, name).inc()
        except Exception:
            pass

    def _log(self, event, assistant):
        try:
            logger.info(
                event,
                extra={
                    "assistant_id": str(assistant.id),
                    "assistant_slug": assistant.slug,
                    "status": assistant.status.value,
                    "visibility": assistant.visibility.value,
                },
            )
        except Exception:
            pass
