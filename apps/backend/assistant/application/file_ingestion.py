import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from assistant.domain.file_fingerprint import ContentStatus, FileFingerprint

logger = logging.getLogger(__name__)


class IdempotentFileRequestConflict(RuntimeError):
    pass


class InvalidFileIdempotencyKey(ValueError):
    pass


class FileIngestionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class FileIngestionRequest:
    doc_type: str
    access_roles: tuple[str, ...]
    upload_path: str
    original_filename: str
    mime_type: str
    fingerprint: FileFingerprint
    checksum_calculated_at: datetime
    document_id: str | None = None
    force_reindex: bool = False
    idempotency_key: str | None = None


@dataclass(frozen=True)
class FileIngestionResult:
    document_id: str
    ingestion_job_id: UUID
    content_status: ContentStatus
    deduplicated: bool
    ingestion_required: bool
    ingestion_in_progress: bool
    force_reindex: bool


class FileIngestionRepository(Protocol):
    def submit(self, request: FileIngestionRequest) -> FileIngestionResult: ...


class FileIngestionService:
    def __init__(self, repository: FileIngestionRepository) -> None:
        self._repository = repository

    def submit(self, request: FileIngestionRequest) -> FileIngestionResult:
        key = request.idempotency_key.strip() if request.idempotency_key is not None else None
        if key is not None and (not key or len(key) > 255):
            raise InvalidFileIdempotencyKey("Idempotency-Key must contain 1 to 255 characters.")
        roles = tuple(sorted(set(role.strip() for role in request.access_roles if role.strip())))
        if not roles:
            roles = ("user",)
        if request.checksum_calculated_at.tzinfo is None:
            raise ValueError("checksum_calculated_at must be timezone-aware.")
        result = self._repository.submit(
            replace(
                request,
                access_roles=roles,
                checksum_calculated_at=request.checksum_calculated_at.astimezone(timezone.utc),
                idempotency_key=key,
            )
        )
        event = {
            ContentStatus.new_content: "fingerprint_calculation_completed",
            ContentStatus.duplicate_content: "duplicate_content_detected",
            ContentStatus.modified_content: "modified_content_detected",
            ContentStatus.forced_reindex: "forced_reindex_requested",
        }[result.content_status]
        logger.info(
            event,
            extra={
                "document_id": result.document_id,
                "ingestion_job_id": str(result.ingestion_job_id),
                "checksum_algorithm": request.fingerprint.algorithm,
                "file_size_bytes": request.fingerprint.file_size_bytes,
                "content_status": result.content_status.value,
                "security_scope_id": ",".join(roles),
            },
        )
        if result.content_status is ContentStatus.duplicate_content:
            event = (
                "active_ingestion_reused"
                if result.ingestion_in_progress
                else "completed_ingestion_reused"
            )
            if result.ingestion_in_progress or not result.ingestion_required:
                logger.info(
                    event,
                    extra={
                        "document_id": result.document_id,
                        "ingestion_job_id": str(result.ingestion_job_id),
                    },
                )
        return result
