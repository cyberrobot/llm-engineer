import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from time import monotonic, sleep
from typing import TypeVar
from uuid import UUID

from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.ingestion_retry import IngestionFailureClassifier, IngestionRetryPolicy
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.application.safe_url import safe_url_origin
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.ingestion_job import IngestionJobRepository
from core.config import IngestionRetrySettings
from core.metrics import IngestionMetrics, ingestion_metrics

logger = logging.getLogger(__name__)
T = TypeVar("T")


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
        classifier: IngestionFailureClassifier | None = None,
        retry_policy: IngestionRetryPolicy | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._repository = repository
        self._website_loader = website_loader
        self._content_processing_service = content_processing_service
        self._knowledge_persistence_service = knowledge_persistence_service
        self._metrics = metrics
        self._classifier = classifier or IngestionFailureClassifier()
        self._retry_policy = retry_policy or IngestionRetryPolicy(
            IngestionRetrySettings(1, 0, 1, 0, False)
        )
        self._sleeper = sleeper

    def start_ingestion(self, source_url: str) -> IngestionJob:
        pipeline_started_at = monotonic()
        job = IngestionJob.create(source_url)
        try:
            self._repository.create(job)
        except Exception as exc:
            durable = self._reload_after_write_error(job.id, stage="job_creation")
            if durable is None:
                self._record_initialization_failure(job, pipeline_started_at)
                raise IngestionFailedError("Knowledge ingestion failed.") from exc
            job = durable
            logger.warning(
                "Ingestion job creation reconciled after write error",
                extra={"ingestion_job_id": str(job.id), "stage": "job_creation"},
            )
        logger.info("Ingestion job created", extra={"ingestion_job_id": str(job.id)})

        if job.status is IngestionStatus.pending:
            job.start()
            try:
                self._repository.update(job)
            except Exception as exc:
                durable = self._reload_after_write_error(job.id, stage="job_start")
                if durable is not None and durable.status is IngestionStatus.running:
                    job = durable
                    logger.warning(
                        "Ingestion running state reconciled after write error",
                        extra={"ingestion_job_id": str(job.id), "stage": "job_start"},
                    )
                else:
                    failure_job = durable or job
                    self._persist_failure(
                        failure_job,
                        "Ingestion job initialization failed.",
                        stage="job_initialization",
                    )
                    self._record_initialization_failure(job, pipeline_started_at)
                    raise IngestionFailedError("Knowledge ingestion failed.") from exc
        elif job.status is not IngestionStatus.running:
            error = RuntimeError("Created ingestion job has an invalid durable state.")
            self._record_initialization_failure(job, pipeline_started_at)
            raise IngestionFailedError("Knowledge ingestion failed.") from error

        logger.info(
            "Ingestion job started",
            extra={
                "ingestion_job_id": str(job.id),
                "source": safe_url_origin(source_url),
            },
        )

        website_loading_duration_ms = 0
        processing_duration_ms = 0
        persistence_duration_ms = 0
        stage = "website_loading"
        failure_message = "Website loading failed."
        try:
            website_started_at = monotonic()
            try:
                documents = self._run_stage(
                    lambda: self._website_loader.load(source_url),
                    step=IngestionStep.parse,
                    job_id=job.id,
                )
            finally:
                website_loading_duration_ms = self._duration_ms(website_started_at)

            stage = "content_processing"
            failure_message = "Content processing failed."
            processing_result = self._content_processing_service.process(documents)
            processing_duration_ms = processing_result.duration_ms

            stage = "knowledge_persistence"
            failure_message = "Knowledge persistence failed."
            persistence_started_at = monotonic()
            prepared = self._run_stage(
                lambda: self._knowledge_persistence_service.prepare(processing_result),
                step=IngestionStep.embed,
                job_id=job.id,
            )
            persistence_result = self._run_stage(
                lambda: self._knowledge_persistence_service.persist_prepared(
                    prepared, started_at=persistence_started_at
                ),
                step=IngestionStep.persist,
                job_id=job.id,
            )
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

        completed_job = deepcopy(job)
        completed_job.complete(
            documents_discovered=processing_result.documents_received,
            documents_processed=processing_result.documents_processed,
            chunks_created=persistence_result.chunks_created,
        )
        total_duration_ms = self._duration_ms(pipeline_started_at)
        try:
            self._repository.update(completed_job)
        except Exception as exc:
            durable = self._reload_after_write_error(job.id, stage="job_completion")
            if durable is not None and self._matches_completion(durable, completed_job):
                job = durable
                logger.warning(
                    "Ingestion completion state reconciled after write error",
                    extra={"ingestion_job_id": str(job.id), "stage": "job_completion"},
                )
            else:
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
                if durable is not None and durable.status in {
                    IngestionStatus.pending,
                    IngestionStatus.running,
                }:
                    self._persist_failure(
                        durable,
                        "Ingestion completion state could not be persisted.",
                        stage="job_completion",
                    )
                raise IngestionFailedError("Knowledge ingestion failed.") from exc
        else:
            job = completed_job
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
        self._persist_failure(job, error_message, stage=stage)
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

    def _persist_failure(self, job: IngestionJob, error_message: str, *, stage: str) -> bool:
        try:
            job.fail(error_message)
            self._repository.update(job)
        except Exception:
            logger.exception(
                "Ingestion failure state could not be persisted",
                extra={"ingestion_job_id": str(job.id), "stage": stage},
            )
            return False
        return True

    def _reload_after_write_error(self, job_id: UUID, *, stage: str) -> IngestionJob | None:
        try:
            return self._repository.get(job_id)
        except Exception:
            logger.exception(
                "Ingestion job state could not be reconciled",
                extra={"ingestion_job_id": str(job_id), "stage": stage},
            )
            return None

    def _record_initialization_failure(self, job: IngestionJob, pipeline_started_at: float) -> None:
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

    @staticmethod
    def _matches_completion(durable: IngestionJob, expected: IngestionJob) -> bool:
        return (
            durable.status is IngestionStatus.completed
            and durable.documents_discovered == expected.documents_discovered
            and durable.documents_processed == expected.documents_processed
            and durable.chunks_created == expected.chunks_created
        )

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1_000))

    def _run_stage(self, operation: Callable[[], T], *, step: IngestionStep, job_id: UUID) -> T:
        attempt_number = 1
        while True:
            try:
                return operation()
            except Exception as exc:
                failure = self._classifier.classify(exc, step)
                if not self._retry_policy.should_retry(failure, attempt_number):
                    raise
                delay = self._retry_policy.get_delay(attempt_number, failure)
                attempt_number += 1
                logger.info(
                    "ingestion_stage_retry_scheduled",
                    extra={
                        "ingestion_job_id": str(job_id),
                        "step": step.value,
                        "attempt_number": attempt_number,
                        "failure_category": failure.category.value,
                        "failure_code": failure.failure_code,
                        "delay_seconds": delay,
                    },
                )
                self._sleeper(delay)
