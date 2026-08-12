from datetime import datetime

import psycopg

from assistant.application.ingestion_observability import IngestionOperationalStatus
from assistant.application.ports.knowledge_source_repository import KnowledgeSourceRepository
from assistant.domain.assistant_repository import AssistantRepository
from assistant.infrastructure.repositories.ingestion_observability import (
    IngestionOperationalStatusRepository,
)
from operations.domain.administration import (
    AssistantCounts,
    IngestionCounts,
    KnowledgeSourceCounts,
    OperationsDependencyUnavailable,
)


class AssistantSummaryStore:
    def __init__(self, assistants: AssistantRepository) -> None:
        self._assistants = assistants

    def counts(self) -> AssistantCounts:
        try:
            aggregate = self._assistants.aggregate_counts()
            return AssistantCounts(
                total=aggregate.total,
                published=aggregate.published,
            )
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Assistant summary is unavailable.") from exc


class KnowledgeSourceSummaryStore:
    def __init__(self, repository: KnowledgeSourceRepository, *, configured: bool = True) -> None:
        self._repository = repository
        self._configured = configured

    def counts(self) -> KnowledgeSourceCounts:
        if not self._configured:
            raise OperationsDependencyUnavailable("Knowledge source summary is unavailable.")
        try:
            aggregate = self._repository.aggregate_counts()
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable(
                "Knowledge source summary is unavailable."
            ) from exc
        # Knowledge sources currently have enabled/disabled retrieval state only.
        # A failed count must remain unavailable instead of being inferred from jobs.
        return KnowledgeSourceCounts(
            total=aggregate.total,
            enabled=aggregate.enabled,
            failed=None,
        )


class IngestionSummaryStore:
    def __init__(self, repository: IngestionOperationalStatusRepository) -> None:
        self._repository = repository

    def counts(self, now: datetime) -> IngestionCounts:
        try:
            status = self._repository.get(now=now)
        except psycopg.Error as exc:
            raise OperationsDependencyUnavailable("Ingestion summary is unavailable.") from exc
        return self._project(status)

    @staticmethod
    def _project(status: IngestionOperationalStatus) -> IngestionCounts:
        return IngestionCounts(
            queued=status.queued_jobs,
            running=status.running_jobs,
            recoverable=status.recoverable_jobs,
            failed=status.failed_jobs,
            oldest_queued_age_seconds=status.oldest_queued_age_seconds,
            workers_observed=status.workers_observed,
        )
