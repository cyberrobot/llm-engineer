import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable
from uuid import UUID, uuid4

import psycopg

from assistant.application.file_ingestion import (
    FileIngestionRequest,
    FileIngestionResult,
    FileIngestionUnavailable,
    IdempotentFileRequestConflict,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.file_fingerprint import ContentStatus, FileFingerprint
from assistant.domain.ingestion_status import IngestionStatus
from infrastructure.database.connection import get_connection

ACTIVE_STATUSES = frozenset({IngestionStatus.queued, IngestionStatus.running})
logger = logging.getLogger(__name__)


@dataclass
class StoredFileDocument:
    id: str
    doc_type: str
    access_roles: tuple[str, ...]
    upload_path: str
    original_filename: str
    mime_type: str
    fingerprint: FileFingerprint


@dataclass
class StoredFileJob:
    job: DocumentIngestionJob
    request_checksum: str
    force_reindex: bool
    trigger_reason: str


@dataclass(frozen=True)
class StoredFileRequest:
    checksum: str
    force_reindex: bool
    result: FileIngestionResult


class InMemoryFileIngestionRepository:
    def __init__(self) -> None:
        self._documents: dict[str, StoredFileDocument] = {}
        self._jobs: dict[UUID, StoredFileJob] = {}
        self._idempotency: dict[str, StoredFileRequest] = {}
        self._lock = RLock()

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def job_count(self) -> int:
        return len(self._jobs)

    def get_document(self, document_id: str) -> StoredFileDocument:
        return deepcopy(self._documents[document_id])

    def set_job_status(self, job_id: UUID, status: IngestionStatus) -> None:
        stored = self._jobs[job_id]
        if status is IngestionStatus.running:
            stored.job.mark_running()
        elif status is IngestionStatus.completed:
            stored.job.mark_running()
            stored.job.mark_completed()
        elif status is IngestionStatus.failed:
            stored.job.mark_running()
            stored.job.mark_failed("test_failure", "Test ingestion failure.")
        elif status is IngestionStatus.cancelled:
            stored.job.mark_cancelled()
        else:
            raise ValueError(f"Unsupported test status: {status}")

    def submit(self, request: FileIngestionRequest) -> FileIngestionResult:
        with self._lock:
            replay = self._idempotent_replay(request)
            if replay is not None:
                return replay

            match = next(
                (
                    document
                    for document in self._documents.values()
                    if document.access_roles == request.access_roles
                    and document.fingerprint == request.fingerprint
                ),
                None,
            )
            if match is not None:
                return self._remember(request, self._for_matching_document(match.id, request))

            existing = self._documents.get(request.document_id or "")
            status = ContentStatus.new_content
            if existing is not None:
                if existing.access_roles != request.access_roles:
                    raise IdempotentFileRequestConflict(
                        "The document belongs to a different access scope."
                    )
                existing.doc_type = request.doc_type
                existing.upload_path = request.upload_path
                existing.original_filename = request.original_filename
                existing.mime_type = request.mime_type
                existing.fingerprint = request.fingerprint
                document_id = existing.id
                status = ContentStatus.modified_content
            else:
                document_id = request.document_id or str(uuid4())
                self._documents[document_id] = StoredFileDocument(
                    document_id,
                    request.doc_type,
                    request.access_roles,
                    request.upload_path,
                    request.original_filename,
                    request.mime_type,
                    request.fingerprint,
                )
            return self._remember(request, self._create_job(document_id, request, status))

    def _for_matching_document(
        self, document_id: str, request: FileIngestionRequest
    ) -> FileIngestionResult:
        jobs = [
            stored.job for stored in self._jobs.values() if stored.job.document_id == document_id
        ]
        active = next((job for job in jobs if job.status in ACTIVE_STATUSES), None)
        if active is not None:
            return self._result(
                active,
                ContentStatus.forced_reindex
                if request.force_reindex
                else ContentStatus.duplicate_content,
                ingestion_required=False,
                in_progress=True,
                force=request.force_reindex,
            )
        latest = jobs[-1] if jobs else None
        if (
            latest is not None
            and latest.status is IngestionStatus.completed
            and not request.force_reindex
        ):
            return self._result(
                latest,
                ContentStatus.duplicate_content,
                ingestion_required=False,
                in_progress=False,
                force=False,
            )
        status = (
            ContentStatus.forced_reindex
            if request.force_reindex
            else ContentStatus.duplicate_content
        )
        return self._create_job(document_id, request, status)

    def _create_job(
        self, document_id: str, request: FileIngestionRequest, status: ContentStatus
    ) -> FileIngestionResult:
        job = DocumentIngestionJob.create(document_id, idempotency_key=request.idempotency_key)
        trigger = "FAILED_RECOVERY" if status is ContentStatus.duplicate_content else status.value
        self._jobs[job.id] = StoredFileJob(
            job, request.fingerprint.checksum, request.force_reindex, trigger
        )
        return self._result(
            job,
            status,
            ingestion_required=True,
            in_progress=False,
            force=request.force_reindex,
        )

    def _idempotent_replay(self, request: FileIngestionRequest) -> FileIngestionResult | None:
        if request.idempotency_key is None:
            return None
        stored = self._idempotency.get(request.idempotency_key)
        if stored is None:
            return None
        if (
            stored.checksum != request.fingerprint.checksum
            or stored.force_reindex != request.force_reindex
        ):
            raise IdempotentFileRequestConflict(
                "Idempotency key was used for different file content or re-index intent."
            )
        return stored.result

    def _remember(
        self, request: FileIngestionRequest, result: FileIngestionResult
    ) -> FileIngestionResult:
        if request.idempotency_key is not None:
            self._idempotency[request.idempotency_key] = StoredFileRequest(
                request.fingerprint.checksum, request.force_reindex, result
            )
        return result

    @staticmethod
    def _result(
        job: DocumentIngestionJob,
        status: ContentStatus,
        *,
        ingestion_required: bool,
        in_progress: bool,
        force: bool,
    ) -> FileIngestionResult:
        return FileIngestionResult(
            job.document_id,
            job.id,
            status,
            status is ContentStatus.duplicate_content and not ingestion_required,
            ingestion_required,
            in_progress,
            force,
        )


class PostgresFileIngestionRepository:
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def submit(self, request: FileIngestionRequest) -> FileIngestionResult:
        try:
            return self._submit_once(request)
        except psycopg.errors.UniqueViolation:
            # Fingerprint and active-job constraints are the final race safeguard.
            try:
                result = self._submit_once(request)
                logger.info(
                    "deduplication_race_resolved",
                    extra={
                        "document_id": result.document_id,
                        "ingestion_job_id": str(result.ingestion_job_id),
                    },
                )
                return result
            except psycopg.Error as exc:
                raise FileIngestionUnavailable(
                    "Concurrent file-ingestion resolution failed."
                ) from exc
        except psycopg.Error as exc:
            raise FileIngestionUnavailable("File-ingestion persistence failed.") from exc

    def _submit_once(self, request: FileIngestionRequest) -> FileIngestionResult:
        with self._connection_factory() as connection:
            if request.idempotency_key is not None:
                replay = connection.execute(
                    """
                    SELECT ingestion_job_id, document_id, request_checksum, force_reindex,
                           content_status, deduplicated, ingestion_required,
                           ingestion_in_progress
                    FROM ingestion_file_requests WHERE idempotency_key = %s
                    """,
                    (request.idempotency_key,),
                ).fetchone()
                if replay is not None:
                    return self._replay_result(replay, request)

            match = connection.execute(
                """
                SELECT id FROM documents
                WHERE assistant_id = %s AND access_roles = %s::jsonb AND checksum_algorithm = %s
                  AND checksum = %s AND file_size_bytes = %s
                ORDER BY created_at, id LIMIT 1
                """,
                (
                    str(REDMOOR_ASSISTANT_ID),
                    json.dumps(request.access_roles),
                    request.fingerprint.algorithm,
                    request.fingerprint.checksum,
                    request.fingerprint.file_size_bytes,
                ),
            ).fetchone()
            if match is not None:
                result = self._matching_result(connection, str(match[0]), request)
                self._record_request(connection, request, result)
                return result

            document_id = request.document_id or str(uuid4())
            existing = connection.execute(
                """SELECT access_roles FROM documents
                   WHERE id = %s AND assistant_id = %s FOR UPDATE""",
                (document_id, str(REDMOOR_ASSISTANT_ID)),
            ).fetchone()
            content_status = ContentStatus.new_content
            values = (
                request.doc_type,
                json.dumps(request.access_roles),
                request.upload_path,
                request.original_filename,
                request.mime_type,
                request.fingerprint.algorithm,
                request.fingerprint.checksum,
                request.fingerprint.file_size_bytes,
                request.checksum_calculated_at,
            )
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, doc_type, access_roles, status, upload_path, original_filename,
                        mime_type, checksum_algorithm, checksum, file_size_bytes,
                        checksum_calculated_at, assistant_id
                    ) VALUES (%s, %s, %s::jsonb, 'uploaded', %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (document_id, *values, str(REDMOOR_ASSISTANT_ID)),
                )
            else:
                if tuple(existing[0]) != request.access_roles:
                    raise IdempotentFileRequestConflict(
                        "The document belongs to a different access scope."
                    )
                content_status = ContentStatus.modified_content
                connection.execute(
                    """
                    UPDATE documents SET doc_type = %s, access_roles = %s::jsonb,
                        upload_path = %s, original_filename = %s, mime_type = %s,
                        checksum_algorithm = %s, checksum = %s, file_size_bytes = %s,
                        checksum_calculated_at = %s, updated_at = NOW()
                    WHERE id = %s AND assistant_id = %s
                    """,
                    (*values, document_id, str(REDMOOR_ASSISTANT_ID)),
                )
            result = self._insert_job(connection, document_id, request, content_status)
            self._record_request(connection, request, result)
            return result

    def _matching_result(
        self, connection: Any, document_id: str, request: FileIngestionRequest
    ) -> FileIngestionResult:
        rows = connection.execute(
            """
            SELECT id, document_id, status, request_checksum, force_reindex, trigger_reason
            FROM document_ingestion_jobs WHERE document_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (document_id,),
        ).fetchall()
        active = next((row for row in rows if IngestionStatus(row[2]) in ACTIVE_STATUSES), None)
        if active is not None:
            status = (
                ContentStatus.forced_reindex
                if request.force_reindex
                else ContentStatus.duplicate_content
            )
            return self._row_result(active, status, False, True, request.force_reindex)
        latest = rows[0] if rows else None
        if (
            latest is not None
            and IngestionStatus(latest[2]) is IngestionStatus.completed
            and not request.force_reindex
        ):
            return self._row_result(latest, ContentStatus.duplicate_content, False, False, False)
        status = (
            ContentStatus.forced_reindex
            if request.force_reindex
            else ContentStatus.duplicate_content
        )
        return self._insert_job(connection, document_id, request, status)

    def _insert_job(
        self,
        connection: Any,
        document_id: str,
        request: FileIngestionRequest,
        status: ContentStatus,
    ) -> FileIngestionResult:
        job_id = uuid4()
        trigger = "FAILED_RECOVERY" if status is ContentStatus.duplicate_content else status.value
        connection.execute(
            """
            INSERT INTO document_ingestion_jobs (
                id, document_id, status, retry_count, current_step_attempt_count,
                idempotency_key, request_checksum, force_reindex, trigger_reason,
                created_at, updated_at
            ) VALUES (%s, %s, 'queued', 0, 0, %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                str(job_id),
                document_id,
                request.idempotency_key,
                request.fingerprint.checksum,
                request.force_reindex,
                trigger,
            ),
        )
        return FileIngestionResult(
            document_id,
            job_id,
            status,
            False,
            True,
            False,
            request.force_reindex,
        )

    def _replay_result(
        self, row: tuple[Any, ...], request: FileIngestionRequest
    ) -> FileIngestionResult:
        if row[2] != request.fingerprint.checksum or bool(row[3]) != request.force_reindex:
            raise IdempotentFileRequestConflict(
                "Idempotency key was used for different file content or re-index intent."
            )
        return FileIngestionResult(
            str(row[1]),
            UUID(str(row[0])),
            ContentStatus(row[4]),
            bool(row[5]),
            bool(row[6]),
            bool(row[7]),
            bool(row[3]),
        )

    @staticmethod
    def _record_request(
        connection: Any, request: FileIngestionRequest, result: FileIngestionResult
    ) -> None:
        if request.idempotency_key is None:
            return
        connection.execute(
            """
            INSERT INTO ingestion_file_requests (
                idempotency_key, request_checksum, force_reindex, document_id,
                ingestion_job_id, content_status, deduplicated, ingestion_required,
                ingestion_in_progress
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request.idempotency_key,
                request.fingerprint.checksum,
                request.force_reindex,
                result.document_id,
                str(result.ingestion_job_id),
                result.content_status.value,
                result.deduplicated,
                result.ingestion_required,
                result.ingestion_in_progress,
            ),
        )

    @staticmethod
    def _row_result(
        row: tuple[Any, ...],
        status: ContentStatus,
        ingestion_required: bool,
        in_progress: bool,
        force: bool,
    ) -> FileIngestionResult:
        return FileIngestionResult(
            str(row[1]),
            UUID(str(row[0])),
            status,
            status is ContentStatus.duplicate_content and not ingestion_required,
            ingestion_required,
            in_progress,
            force,
        )
