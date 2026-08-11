from uuid import UUID

from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
    IngestionJobRepositoryFailure,
)
from operations.domain.administration import (
    JobCounts,
    JobPage,
    OperationalJob,
    OperationsDependencyUnavailable,
)


class IngestionJobOperationsStore:
    """Read-only operations projection over the established ingestion repository."""

    def __init__(self, repository: DocumentIngestionJobRepository) -> None:
        self._repository = repository

    def list(self, *, limit: int, offset: int, status: str | None = None) -> JobPage:
        parsed_status = IngestionStatus(status) if status else None
        try:
            page = self._repository.list(limit=limit, offset=offset, status=parsed_status)
        except IngestionJobRepositoryFailure as exc:
            raise OperationsDependencyUnavailable("Job visibility is unavailable.") from exc
        return JobPage(tuple(self._project(job) for job in page.items), page.total, limit, offset)

    def get(self, job_id: UUID) -> OperationalJob | None:
        try:
            job = self._repository.get_by_id(job_id)
        except IngestionJobRepositoryFailure as exc:
            raise OperationsDependencyUnavailable("Job visibility is unavailable.") from exc
        return self._project(job) if job else None

    def counts(self) -> JobCounts:
        try:
            running = self._repository.list(limit=1, offset=0, status=IngestionStatus.running).total
            failed = self._repository.list(limit=1, offset=0, status=IngestionStatus.failed).total
        except IngestionJobRepositoryFailure as exc:
            raise OperationsDependencyUnavailable("Job visibility is unavailable.") from exc
        return JobCounts(running=running, failed=failed)

    @staticmethod
    def _project(job: DocumentIngestionJob) -> OperationalJob:
        return OperationalJob(
            id=job.id,
            status=job.status.value,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            retry_count=job.retry_count,
            last_error=job.failure_code,
        )
