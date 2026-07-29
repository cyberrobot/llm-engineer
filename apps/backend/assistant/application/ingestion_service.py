import logging
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from uuid import UUID

from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.ingestion_job import IngestionJobRepository
from core.metrics import IngestionMetrics, ingestion_metrics

logger = logging.getLogger(__name__)


class IngestionJobNotFound(LookupError):
    """Raised when a requested ingestion job does not exist."""


class IngestionFailedError(RuntimeError):
    """Safe application error raised after a pipeline failure is persisted."""


@dataclass(frozen=True)
class KnowledgeStatus:
    documents: int
    chunks: int
    last_ingestion_at: datetime | None
    last_ingestion_status: IngestionStatus | None


class IngestionService:
    """Coordinate existing website ingestion components and job lifecycle."""

    def __init__(
        self,
        repository: IngestionJobRepository,
        website_loader: WebsiteLoader,
        content_processing_service: ContentProcessingService,
        knowledge_persistence_service: KnowledgePersistenceService,
        *,
        metrics: IngestionMetrics = ingestion_metrics,
    ) -> None:
        self._repository = repository
        self._website_loader = website_loader
        self._content_processing_service = content_processing_service
        self._knowledge_persistence_service = knowledge_persistence_service
        self._metrics = metrics

    def start_ingestion(self, source_url: str) -> IngestionJob:
        pipeline_started_at = monotonic()
        job = IngestionJob.create(source_url)
        try:
            self._repository.create(job)
            job.start()
            self._repository.update(job)
        except Exception as exc:
            total_duration_ms = self._duration_ms(pipeline_started_at)
            self._metrics.record_failure(total_duration_ms=total_duration_ms)
            logger.exception(
                "Ingestion job could not be initialized",
                extra={
                    "ingestion_job_id": str(job.id),
                    "stage": "job_initialization",
                    "total_duration_ms": total_duration_ms,
                },
            )
            raise IngestionFailedError("Knowledge ingestion failed.") from exc
        logger.info("Ingestion job created", extra={"ingestion_job_id": str(job.id)})
        logger.info(
            "Ingestion job started",
            extra={"ingestion_job_id": str(job.id), "source_url": source_url},
        )

        website_loading_duration_ms = 0
        processing_duration_ms = 0
        persistence_duration_ms = 0
        stage = "website_loading"
        failure_message = "Website loading failed."
        try:
            website_started_at = monotonic()
            try:
                documents = self._website_loader.load(source_url)
            finally:
                website_loading_duration_ms = self._duration_ms(website_started_at)

            stage = "content_processing"
            failure_message = "Content processing failed."
            processing_result = self._content_processing_service.process(documents)
            processing_duration_ms = processing_result.duration_ms

            stage = "knowledge_persistence"
            failure_message = "Knowledge persistence failed."
            persistence_result = self._knowledge_persistence_service.persist(processing_result)
            persistence_duration_ms = persistence_result.duration_ms
        except Exception as exc:
            total_duration_ms = self._duration_ms(pipeline_started_at)
            self._fail_job(
                job,
                failure_message,
                stage=stage,
                pipeline_started_at=pipeline_started_at,
                website_loading_duration_ms=website_loading_duration_ms,
                processing_duration_ms=processing_duration_ms,
                persistence_duration_ms=persistence_duration_ms,
            )
            self._metrics.record_failure(
                total_duration_ms=total_duration_ms,
                website_duration_ms=website_loading_duration_ms,
                processing_duration_ms=processing_duration_ms,
                persistence_duration_ms=persistence_duration_ms,
            )
            raise IngestionFailedError("Knowledge ingestion failed.") from exc

        job.complete(
            documents_discovered=processing_result.documents_received,
            documents_processed=processing_result.documents_processed,
            chunks_created=persistence_result.chunks_created,
        )
        total_duration_ms = self._duration_ms(pipeline_started_at)
        try:
            self._repository.update(job)
        except Exception as exc:
            self._metrics.record_failure(
                total_duration_ms=total_duration_ms,
                website_duration_ms=website_loading_duration_ms,
                processing_duration_ms=processing_duration_ms,
                persistence_duration_ms=persistence_duration_ms,
            )
            logger.exception(
                "Ingestion completion state could not be persisted",
                extra={
                    "ingestion_job_id": str(job.id),
                    "stage": "job_completion",
                    "total_duration_ms": total_duration_ms,
                },
            )
            raise IngestionFailedError("Knowledge ingestion failed.") from exc
        self._metrics.record_success(
            total_duration_ms=total_duration_ms,
            website_duration_ms=website_loading_duration_ms,
            processing_duration_ms=processing_duration_ms,
            persistence_duration_ms=persistence_duration_ms,
            embedding_duration_ms=persistence_result.embedding_duration_ms,
            pages_processed=processing_result.documents_processed,
            pages_skipped=processing_result.documents_skipped,
            documents_persisted=(
                persistence_result.documents_created + persistence_result.documents_updated
            ),
            chunks_persisted=persistence_result.chunks_created,
            embeddings_generated=persistence_result.embeddings_generated,
        )
        logger.info(
            "Ingestion job completed",
            extra={
                "ingestion_job_id": str(job.id),
                "documents_discovered": processing_result.documents_received,
                "documents_processed": processing_result.documents_processed,
                "documents_skipped": processing_result.documents_skipped,
                "documents_created": persistence_result.documents_created,
                "documents_updated": persistence_result.documents_updated,
                "documents_unchanged": persistence_result.documents_unchanged,
                "chunks_created": persistence_result.chunks_created,
                "website_loading_duration_ms": website_loading_duration_ms,
                "processing_duration_ms": processing_duration_ms,
                "persistence_duration_ms": persistence_duration_ms,
                "embedding_duration_ms": persistence_result.embedding_duration_ms,
                "documents_persisted": (
                    persistence_result.documents_created + persistence_result.documents_updated
                ),
                "total_duration_ms": total_duration_ms,
            },
        )
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

    def _fail_job(
        self,
        job: IngestionJob,
        error_message: str,
        *,
        stage: str,
        pipeline_started_at: float,
        website_loading_duration_ms: int,
        processing_duration_ms: int,
        persistence_duration_ms: int,
    ) -> None:
        job.fail(error_message)
        try:
            self._repository.update(job)
        except Exception:
            logger.exception(
                "Ingestion failure state could not be persisted",
                extra={"ingestion_job_id": str(job.id), "stage": stage},
            )
        logger.exception(
            "Ingestion job failed",
            extra={
                "ingestion_job_id": str(job.id),
                "stage": stage,
                "website_loading_duration_ms": website_loading_duration_ms,
                "processing_duration_ms": processing_duration_ms,
                "persistence_duration_ms": persistence_duration_ms,
                "total_duration_ms": self._duration_ms(pipeline_started_at),
            },
        )

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1_000))
