import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.ingestion_job import IngestionJobRepository

logger = logging.getLogger(__name__)


class IngestionJobNotFound(LookupError):
    """Raised when a requested ingestion job does not exist."""


@dataclass(frozen=True)
class KnowledgeStatus:
    documents: int
    chunks: int
    last_ingestion_at: datetime | None
    last_ingestion_status: IngestionStatus | None


class IngestionService:
    """Coordinate ingestion job lifecycle independently of future processing."""

    def __init__(self, repository: IngestionJobRepository) -> None:
        self._repository = repository

    def start_ingestion(self, source_url: str) -> IngestionJob:
        job = IngestionJob.create(source_url)
        self._repository.create(job)
        logger.info("Ingestion job created", extra={"ingestion_job_id": str(job.id)})

        # This chunk proves the public lifecycle only. Future processing will replace
        # this zero-result completion without changing the route contract.
        job.start()
        job.complete(documents_discovered=0, documents_processed=0, chunks_created=0)
        self._repository.update(job)
        logger.info("Ingestion job completed", extra={"ingestion_job_id": str(job.id)})
        return job

    def get_job(self, job_id: UUID) -> IngestionJob:
        job = self._repository.get(job_id)
        if job is None:
            raise IngestionJobNotFound("Ingestion job not found.")
        return job

    def fail_job(self, job_id: UUID, error_message: str) -> IngestionJob:
        job = self.get_job(job_id)
        job.fail(error_message)
        self._repository.update(job)
        logger.error("Ingestion job failed", extra={"ingestion_job_id": str(job.id)})
        return job

    def get_knowledge_status(self) -> KnowledgeStatus:
        latest = self._repository.latest()
        if latest is None:
            return KnowledgeStatus(
                documents=0,
                chunks=0,
                last_ingestion_at=None,
                last_ingestion_status=None,
            )
        return KnowledgeStatus(
            documents=latest.documents_processed,
            chunks=latest.chunks_created,
            last_ingestion_at=latest.completed_at,
            last_ingestion_status=latest.status,
        )
