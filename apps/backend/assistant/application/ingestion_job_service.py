import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
    DocumentRecordNotFound,
    IngestionJobRepositoryFailure,
)
from core.metrics import IngestionOperationalMetrics, ingestion_operational_metrics

IDEMPOTENCY_KEY_MAX_LENGTH = 255
logger = logging.getLogger(__name__)


class IngestionJobNotFound(LookupError):
    pass


class DocumentNotFound(LookupError):
    pass


class InvalidIdempotencyKey(ValueError):
    pass


class IdempotencyKeyConflict(RuntimeError):
    pass


class IngestionJobUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionJobList:
    items: list[DocumentIngestionJob]
    total: int
    limit: int
    offset: int


class DocumentIngestionJobService:
    def __init__(
        self,
        repository: DocumentIngestionJobRepository,
        *,
        metrics: IngestionOperationalMetrics = ingestion_operational_metrics,
    ) -> None:
        self._repository = repository
        self._metrics = metrics

    def create(
        self, document_id: str, *, idempotency_key: str | None = None
    ) -> DocumentIngestionJob:
        key = self._normalise_idempotency_key(idempotency_key)
        try:
            if not self._repository.document_exists(document_id):
                raise DocumentNotFound(document_id)
            if key is not None:
                existing = self._repository.get_by_idempotency_key(key)
                if existing is not None:
                    return self._resolve_idempotent_request(existing, document_id)
            candidate = DocumentIngestionJob.create(document_id, idempotency_key=key)
            created = self._repository.create(candidate)
            if created.id == candidate.id:
                logger.info(
                    "ingestion_job_created",
                    extra={
                        "ingestion_job_id": str(created.id),
                        "document_id": created.document_id,
                        "status": created.status.value,
                    },
                )
                try:
                    self._metrics.job_created()
                except Exception:
                    logger.warning(
                        "ingestion_telemetry_export_failed", extra={"reason": "job_created"}
                    )
            return self._resolve_idempotent_request(created, document_id)
        except DocumentRecordNotFound as exc:
            raise DocumentNotFound(document_id) from exc
        except IngestionJobRepositoryFailure as exc:
            raise IngestionJobUnavailable("Ingestion job storage is unavailable.") from exc

    def get(self, job_id: UUID) -> DocumentIngestionJob:
        try:
            job = self._repository.get_by_id(job_id)
        except IngestionJobRepositoryFailure as exc:
            raise IngestionJobUnavailable("Ingestion job storage is unavailable.") from exc
        if job is None:
            raise IngestionJobNotFound(job_id)
        return job

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
        document_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        failed_step: IngestionStep | None = None,
    ) -> IngestionJobList:
        try:
            page = self._repository.list(
                limit=limit,
                offset=offset,
                status=status,
                document_id=document_id,
                created_from=created_from,
                created_to=created_to,
                failed_step=failed_step,
            )
        except IngestionJobRepositoryFailure as exc:
            raise IngestionJobUnavailable("Ingestion job storage is unavailable.") from exc
        return IngestionJobList(page.items, page.total, limit, offset)

    @staticmethod
    def _normalise_idempotency_key(key: str | None) -> str | None:
        if key is None:
            return None
        normalised = key.strip()
        if not normalised or len(normalised) > IDEMPOTENCY_KEY_MAX_LENGTH:
            raise InvalidIdempotencyKey(
                f"Idempotency-Key must contain 1 to {IDEMPOTENCY_KEY_MAX_LENGTH} characters."
            )
        return normalised

    @staticmethod
    def _resolve_idempotent_request(
        job: DocumentIngestionJob, document_id: str
    ) -> DocumentIngestionJob:
        if job.document_id != document_id:
            raise IdempotencyKeyConflict("Idempotency key was used for another document.")
        return job
