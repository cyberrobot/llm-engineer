import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from assistant.domain.assistant import (
    REDMOOR_ASSISTANT_ID,
    Assistant,
    AssistantStatus,
    AssistantVisibility,
)
from assistant.domain.assistant_repository import (
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    AssistantNotFound,
    AssistantRepository,
    DuplicateAssistantSlug,
)
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
    def deletion_allowed(self) -> bool:
        return self.assistant.id != REDMOOR_ASSISTANT_ID and not self.has_dependencies


class AssistantAdministrationService:
    def __init__(
        self,
        repository: AssistantRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self.repository, self.clock, self.id_factory = repository, clock, id_factory

    def list_assistants(
        self,
        *,
        limit: int,
        offset: int,
        status: AssistantStatus | None = None,
        visibility: AssistantVisibility | None = None,
    ) -> tuple[list[Assistant], int]:
        return self.repository.list(
            limit=limit, offset=offset, status=status, visibility=visibility
        )

    def get_assistant(self, assistant_id: UUID) -> AssistantView:
        try:
            assistant = self.repository.get_by_id(assistant_id)
        except AssistantNotFound:
            self._metric("detail", "not_found")
            raise
        dependencies = self.repository.dependency_summary(assistant_id)
        return AssistantView(
            assistant,
            dependencies.knowledge_source_count,
            dependencies.has_dependencies,
        )

    def create_assistant(
        self,
        *,
        slug: str,
        name: str,
        status: AssistantStatus = AssistantStatus.inactive,
        visibility: AssistantVisibility = AssistantVisibility.private,
    ) -> Assistant:
        now = self.clock()
        assistant = Assistant(self.id_factory(), slug, name, status, visibility, now, now)
        try:
            result = self.repository.create(assistant)
        except DuplicateAssistantSlug:
            self._metric("create", "conflict")
            self._log("assistant_duplicate_slug_conflict", assistant)
            raise
        except Exception:
            self._metric("create", "failure")
            raise
        self._metric("create", "success")
        self._log("assistant_created", result)
        return result

    def update_assistant(
        self,
        assistant_id: UUID,
        *,
        concurrency_token: datetime,
        name: str | None = None,
        status: AssistantStatus | None = None,
        visibility: AssistantVisibility | None = None,
    ) -> Assistant:
        if name is None and status is None and visibility is None:
            raise EmptyAssistantUpdate("At least one mutable field is required.")
        try:
            current = self.repository.get_by_id(assistant_id)
        except AssistantNotFound:
            self._metric("update", "not_found")
            raise
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
        except AssistantConcurrentUpdate:
            self._metric("update", "conflict")
            self._log("assistant_concurrent_update_conflict", current)
            raise
        except AssistantNotFound:
            self._metric("update", "not_found")
            raise
        except Exception:
            self._metric("update", "failure")
            raise
        self._metric("update", "success")
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

    def delete_assistant(self, assistant_id: UUID) -> None:
        if assistant_id == REDMOOR_ASSISTANT_ID:
            self._metric("delete", "conflict")
            self._log_event(
                "assistant_protected_deletion", assistant_id=assistant_id, outcome_code="protected"
            )
            raise ProtectedAssistantDeletion("The seeded assistant cannot be deleted.")
        try:
            self.repository.delete(assistant_id)
        except AssistantDeletionBlocked:
            self._metric("delete", "conflict")
            self._log_event(
                "assistant_deletion_blocked", assistant_id=assistant_id, outcome_code="dependencies"
            )
            raise
        except AssistantNotFound:
            self._metric("delete", "not_found")
            raise
        except Exception:
            self._metric("delete", "failure")
            raise
        self._metric("delete", "success")
        self._log_event("assistant_deleted", assistant_id=assistant_id, outcome_code="success")

    def _metric(self, operation: str, outcome: str) -> None:
        try:
            assistant_administration_metrics.operations.labels(
                operation=operation, outcome=outcome
            ).inc()
        except Exception:
            pass

    def _log(self, event: str, assistant: Assistant) -> None:
        self._log_event(
            event,
            assistant_id=assistant.id,
            assistant_slug=assistant.slug,
            status=assistant.status.value,
            visibility=assistant.visibility.value,
        )

    def _log_event(self, event: str, **fields: object) -> None:
        try:
            safe_fields = dict(fields)
            if "assistant_id" in safe_fields:
                safe_fields["assistant_id"] = str(safe_fields["assistant_id"])
            logger.info(event, extra=safe_fields)
        except Exception:
            pass
