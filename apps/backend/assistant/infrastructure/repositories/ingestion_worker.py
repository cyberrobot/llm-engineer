from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg

from assistant.application.ingestion_worker import IngestionJobClaim, IngestionWorkerRepository
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.infrastructure.repositories.document_ingestion_job import (
    IngestionJobRepositoryFailure,
    PostgresDocumentIngestionJobRepository,
)
from infrastructure.database.connection import get_connection


class IngestionOwnershipLost(IngestionJobRepositoryFailure):
    """A claim was expired, cancelled, completed, or replaced by another worker."""


class PostgresIngestionWorkerRepository(IngestionWorkerRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def claim_next(
        self, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim | None:
        return self._claim(worker_id, lease_duration, now, job_id=None)

    def claim_job(
        self,
        job_id: UUID,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime,
    ) -> IngestionJobClaim | None:
        return self._claim(worker_id, lease_duration, now, job_id=job_id)

    def _claim(
        self,
        worker_id: str,
        lease_duration: timedelta,
        now: datetime,
        *,
        job_id: UUID | None,
    ) -> IngestionJobClaim | None:
        target_clause = "AND jobs.id = %s" if job_id is not None else ""
        parameters = (str(job_id), now) if job_id is not None else (now,)
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    f"""
                    SELECT jobs.id, jobs.document_id, jobs.status
                    FROM document_ingestion_jobs AS jobs
                    JOIN documents ON documents.id = jobs.document_id
                    WHERE documents.source_url IS NOT NULL
                      {target_clause}
                      AND (
                           jobs.status = 'queued'
                       OR (
                            jobs.status = 'running'
                            AND (
                                jobs.lease_expires_at IS NULL
                                OR jobs.lease_expires_at <= %s
                            )
                       )
                      )
                    ORDER BY jobs.created_at ASC, jobs.id ASC
                    FOR UPDATE OF jobs SKIP LOCKED
                    LIMIT 1
                    """,
                    parameters,
                ).fetchone()
                if row is None:
                    return None
                recovered = row[2] == "running"
                lease_expires_at = now + lease_duration
                claimed = connection.execute(
                    """
                    UPDATE document_ingestion_jobs
                    SET status = 'running',
                        started_at = COALESCE(started_at, %s),
                        current_step_attempt_count = CASE
                            WHEN %s AND current_step IS NOT NULL
                            THEN current_step_attempt_count + 1
                            ELSE current_step_attempt_count
                        END,
                        worker_id = %s,
                        claimed_at = %s,
                        lease_expires_at = %s,
                        last_heartbeat_at = %s,
                        claim_version = claim_version + 1,
                        updated_at = %s
                    WHERE id = %s
                    RETURNING claim_version
                    """,
                    (
                        now,
                        recovered,
                        worker_id,
                        now,
                        lease_expires_at,
                        now,
                        now,
                        str(row[0]),
                    ),
                ).fetchone()
            return IngestionJobClaim(
                UUID(str(row[0])),
                str(row[1]),
                worker_id,
                int(claimed[0]),
                now,
                lease_expires_at,
                recovered,
            )
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job claim failed.") from exc

    def renew_lease(
        self, claim: IngestionJobClaim, lease_duration: timedelta, now: datetime
    ) -> bool:
        try:
            with self._connection_factory() as connection:
                result = connection.execute(
                    """
                    UPDATE document_ingestion_jobs
                    SET last_heartbeat_at = %s,
                        lease_expires_at = %s,
                        updated_at = %s
                    WHERE id = %s
                      AND status = 'running'
                      AND worker_id = %s
                      AND claim_version = %s
                      AND lease_expires_at > %s
                    """,
                    (
                        now,
                        now + lease_duration,
                        now,
                        str(claim.job_id),
                        claim.worker_id,
                        claim.claim_version,
                        now,
                    ),
                )
            return result.rowcount == 1
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job heartbeat failed.") from exc


class FencedPostgresDocumentIngestionJobRepository(PostgresDocumentIngestionJobRepository):
    """Pipeline repository whose writes require the exact active worker claim."""

    def __init__(
        self,
        claim: IngestionJobClaim,
        connection_factory: Callable[[], Any] = get_connection,
    ) -> None:
        super().__init__(connection_factory)
        self._claim = claim

    def update(self, job: DocumentIngestionJob) -> None:
        terminal = job.status.value in {"completed", "failed", "cancelled"}
        try:
            with self._connection_factory() as connection:
                result = connection.execute(
                    """
                    UPDATE document_ingestion_jobs
                    SET status = %s, current_step = %s, last_completed_step = %s,
                        retry_count = GREATEST(retry_count, %s),
                        current_step_attempt_count = %s, last_attempted_at = %s,
                        failure_code = %s, failure_message = %s, started_at = %s,
                        completed_at = %s, updated_at = %s,
                        worker_id = CASE WHEN %s THEN NULL ELSE worker_id END,
                        lease_expires_at = CASE WHEN %s THEN NULL ELSE lease_expires_at END
                    WHERE id = %s
                      AND status = 'running'
                      AND worker_id = %s
                      AND claim_version = %s
                      AND lease_expires_at > NOW()
                    """,
                    (
                        job.status.value,
                        job.current_step.value if job.current_step else None,
                        job.last_completed_step.value if job.last_completed_step else None,
                        job.retry_count,
                        job.current_step_attempt_count,
                        job.last_attempted_at,
                        job.failure_code,
                        job.failure_message,
                        job.started_at,
                        job.completed_at,
                        job.updated_at,
                        terminal,
                        terminal,
                        str(job.id),
                        self._claim.worker_id,
                        self._claim.claim_version,
                    ),
                )
            if result.rowcount != 1:
                raise IngestionOwnershipLost("Ingestion job ownership was lost.")
        except IngestionOwnershipLost:
            raise
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job update failed.") from exc

    def record_retry(
        self,
        job_id: UUID,
        step: IngestionStep,
        failure_code: str,
        failure_message: str,
    ) -> DocumentIngestionJob:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    f"""
                    UPDATE document_ingestion_jobs
                    SET retry_count = retry_count + 1,
                        current_step_attempt_count = current_step_attempt_count + 1,
                        failure_code = %s,
                        failure_message = %s,
                        last_attempted_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'running'
                      AND current_step = %s
                      AND worker_id = %s
                      AND claim_version = %s
                      AND lease_expires_at > NOW()
                    RETURNING {self._columns}
                    """,
                    (
                        failure_code,
                        failure_message,
                        str(job_id),
                        step.value,
                        self._claim.worker_id,
                        self._claim.claim_version,
                    ),
                ).fetchone()
            if row is None:
                raise IngestionOwnershipLost("Ingestion job ownership was lost.")
            return self._from_row(row)
        except IngestionOwnershipLost:
            raise
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion retry update failed.") from exc
