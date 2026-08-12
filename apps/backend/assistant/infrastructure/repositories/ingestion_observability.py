from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

import psycopg

from assistant.application.ingestion_observability import IngestionOperationalStatus
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.ingestion_step_execution import (
    IngestionStepExecution,
    IngestionStepExecutionStatus,
)
from infrastructure.database.connection import get_connection


class IngestionStepExecutionRepository:
    def start_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        started_at: datetime,
    ) -> IngestionStepExecution:
        raise NotImplementedError

    def complete_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        raise NotImplementedError

    def fail_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
        failure_code: str,
        retryable: bool,
    ) -> None:
        raise NotImplementedError

    def interrupt_running_attempts(self, job_id: UUID) -> int:
        raise NotImplementedError

    def list_for_job(self, job_id: UUID) -> list[IngestionStepExecution]:
        raise NotImplementedError


class InMemoryIngestionStepExecutionRepository(IngestionStepExecutionRepository):
    def __init__(self) -> None:
        self._attempts: dict[tuple[UUID, IngestionStep, int], IngestionStepExecution] = {}
        self._lock = RLock()

    def start_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        started_at: datetime,
    ) -> IngestionStepExecution:
        attempt = IngestionStepExecution(
            uuid4(),
            job_id,
            step,
            attempt_number,
            IngestionStepExecutionStatus.running,
            started_at,
        )
        key = (job_id, step, attempt_number)
        with self._lock:
            if key in self._attempts:
                raise ValueError("The step attempt already exists.")
            self._attempts[key] = attempt
        return deepcopy(attempt)

    def complete_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        self._finish(
            job_id,
            step,
            attempt_number,
            status=IngestionStepExecutionStatus.completed,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    def fail_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
        failure_code: str,
        retryable: bool,
    ) -> None:
        self._finish(
            job_id,
            step,
            attempt_number,
            status=IngestionStepExecutionStatus.failed,
            completed_at=completed_at,
            duration_ms=duration_ms,
            failure_code=failure_code,
            retryable=retryable,
        )

    def _finish(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        status: IngestionStepExecutionStatus,
        completed_at: datetime,
        duration_ms: int,
        failure_code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        key = (job_id, step, attempt_number)
        with self._lock:
            existing = self._attempts.get(key)
            if existing is None or existing.status is not IngestionStepExecutionStatus.running:
                raise ValueError("Only a running step attempt can receive a terminal result.")
            self._attempts[key] = IngestionStepExecution(
                existing.id,
                existing.ingestion_job_id,
                existing.step,
                existing.attempt_number,
                status,
                existing.started_at,
                completed_at,
                duration_ms,
                failure_code,
                retryable,
            )

    def interrupt_running_attempts(self, job_id: UUID) -> int:
        changed = 0
        with self._lock:
            for key, attempt in tuple(self._attempts.items()):
                if (
                    attempt.ingestion_job_id == job_id
                    and attempt.status is IngestionStepExecutionStatus.running
                ):
                    self._attempts[key] = IngestionStepExecution(
                        attempt.id,
                        attempt.ingestion_job_id,
                        attempt.step,
                        attempt.attempt_number,
                        IngestionStepExecutionStatus.interrupted,
                        attempt.started_at,
                    )
                    changed += 1
        return changed

    def list_for_job(self, job_id: UUID) -> list[IngestionStepExecution]:
        with self._lock:
            attempts = [
                attempt for attempt in self._attempts.values() if attempt.ingestion_job_id == job_id
            ]
            attempts.sort(key=lambda attempt: (attempt.started_at, attempt.attempt_number))
            return deepcopy(attempts)


class PostgresIngestionStepExecutionRepository(IngestionStepExecutionRepository):
    _columns = """id, ingestion_job_id, step, attempt_number, status, started_at,
                  completed_at, duration_ms, failure_code, retryable"""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def start_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        started_at: datetime,
    ) -> IngestionStepExecution:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    f"""
                    INSERT INTO ingestion_step_executions
                        (ingestion_job_id, step, attempt_number, status, started_at)
                    VALUES (%s, %s, %s, 'running', %s)
                    RETURNING {self._columns}
                    """,
                    (str(job_id), step.value, attempt_number, started_at),
                ).fetchone()
            return self._from_row(row)
        except psycopg.errors.UniqueViolation as exc:
            raise ValueError("The step attempt already exists.") from exc

    def complete_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        self._finish(
            job_id, step, attempt_number, completed_at, duration_ms, None, None, "completed"
        )

    def fail_attempt(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        *,
        completed_at: datetime,
        duration_ms: int,
        failure_code: str,
        retryable: bool,
    ) -> None:
        self._finish(
            job_id,
            step,
            attempt_number,
            completed_at,
            duration_ms,
            failure_code,
            retryable,
            "failed",
        )

    def _finish(
        self,
        job_id: UUID,
        step: IngestionStep,
        attempt_number: int,
        completed_at: datetime,
        duration_ms: int,
        failure_code: str | None,
        retryable: bool | None,
        status: str,
    ) -> None:
        with self._connection_factory() as connection:
            result = connection.execute(
                """
                UPDATE ingestion_step_executions
                SET status = %s, completed_at = %s, duration_ms = %s,
                    failure_code = %s, retryable = %s
                WHERE ingestion_job_id = %s AND step = %s AND attempt_number = %s
                  AND status = 'running'
                """,
                (
                    status,
                    completed_at,
                    max(0, duration_ms),
                    failure_code,
                    retryable,
                    str(job_id),
                    step.value,
                    attempt_number,
                ),
            )
        if result.rowcount != 1:
            raise ValueError("Only a running step attempt can receive a terminal result.")

    def interrupt_running_attempts(self, job_id: UUID) -> int:
        with self._connection_factory() as connection:
            result = connection.execute(
                """
                UPDATE ingestion_step_executions SET status = 'interrupted'
                WHERE ingestion_job_id = %s AND status = 'running'
                """,
                (str(job_id),),
            )
        return result.rowcount

    def list_for_job(self, job_id: UUID) -> list[IngestionStepExecution]:
        with self._connection_factory() as connection:
            rows = connection.execute(
                f"""
                SELECT {self._columns} FROM ingestion_step_executions
                WHERE ingestion_job_id = %s ORDER BY started_at ASC, attempt_number ASC
                """,
                (str(job_id),),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: Any) -> IngestionStepExecution:
        return IngestionStepExecution(
            UUID(str(row[0])),
            UUID(str(row[1])),
            IngestionStep(row[2]),
            int(row[3]),
            IngestionStepExecutionStatus(row[4]),
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
        )


class IngestionOperationalStatusRepository:
    def get(self, *, now: datetime) -> IngestionOperationalStatus:
        raise NotImplementedError


class EmptyIngestionOperationalStatusRepository(IngestionOperationalStatusRepository):
    def get(self, *, now: datetime) -> IngestionOperationalStatus:
        return IngestionOperationalStatus(0, 0, 0, 0, 0)


class PostgresIngestionOperationalStatusRepository(IngestionOperationalStatusRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def get(self, *, now: datetime) -> IngestionOperationalStatus:
        with self._connection_factory() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM document_ingestion_jobs WHERE status = 'queued'),
                    (SELECT count(*) FROM document_ingestion_jobs WHERE status = 'running'),
                    (SELECT count(*) FROM document_ingestion_jobs
                     WHERE status = 'running'
                       AND (lease_expires_at IS NULL OR lease_expires_at <= %s)),
                    COALESCE((SELECT EXTRACT(EPOCH FROM (%s - min(created_at)))
                              FROM document_ingestion_jobs WHERE status = 'queued'), 0),
                    (SELECT count(DISTINCT worker_id) FROM document_ingestion_jobs
                     WHERE status = 'running' AND worker_id IS NOT NULL
                       AND lease_expires_at > %s),
                    (SELECT count(*) FROM document_ingestion_jobs WHERE status = 'failed')
                """,
                (now, now, now),
            ).fetchone()
        return IngestionOperationalStatus(
            queued_jobs=int(row[0]),
            running_jobs=int(row[1]),
            recoverable_jobs=int(row[2]),
            oldest_queued_age_seconds=max(0, float(row[3])),
            workers_observed=int(row[4]),
            failed_jobs=int(row[5]),
        )
