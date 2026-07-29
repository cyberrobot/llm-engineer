from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import deepcopy
from threading import RLock
from typing import Any
from uuid import UUID

from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from infrastructure.database.connection import get_connection


class IngestionJobRepository(ABC):
    @abstractmethod
    def create(self, job: IngestionJob) -> None:
        """Persist a new job."""

    @abstractmethod
    def update(self, job: IngestionJob) -> None:
        """Persist the current state of an existing job."""

    @abstractmethod
    def get(self, job_id: UUID) -> IngestionJob | None:
        """Load a job by identifier."""

    @abstractmethod
    def latest(self) -> IngestionJob | None:
        """Load the most recently created job."""


class InMemoryIngestionJobRepository(IngestionJobRepository):
    """Process-local job persistence for environments without a database."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, IngestionJob] = {}
        self._lock = RLock()

    def create(self, job: IngestionJob) -> None:
        with self._lock:
            if job.id in self._jobs:
                raise ValueError(f"Ingestion job {job.id} already exists.")
            self._jobs[job.id] = deepcopy(job)

    def update(self, job: IngestionJob) -> None:
        with self._lock:
            if job.id not in self._jobs:
                raise KeyError(job.id)
            self._jobs[job.id] = deepcopy(job)

    def get(self, job_id: UUID) -> IngestionJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def latest(self) -> IngestionJob | None:
        with self._lock:
            if not self._jobs:
                return None
            return deepcopy(max(self._jobs.values(), key=lambda job: job.created_at))


class PostgresIngestionJobRepository(IngestionJobRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def create(self, job: IngestionJob) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ingestion_jobs (
                        id, source_url, status, documents_discovered,
                        documents_processed, chunks_created, error_message,
                        created_at, started_at, completed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    self._parameters(job),
                )

    def update(self, job: IngestionJob) -> None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_jobs
                    SET source_url = %s,
                        status = %s,
                        documents_discovered = %s,
                        documents_processed = %s,
                        chunks_created = %s,
                        error_message = %s,
                        created_at = %s,
                        started_at = %s,
                        completed_at = %s
                    WHERE id = %s
                    """,
                    (*self._parameters(job)[1:], str(job.id)),
                )
                if cursor.rowcount == 0:
                    raise KeyError(job.id)

    def get(self, job_id: UUID) -> IngestionJob | None:
        return self._fetch_one("WHERE id = %s", (str(job_id),))

    def latest(self) -> IngestionJob | None:
        return self._fetch_one("ORDER BY created_at DESC, id DESC LIMIT 1")

    def _fetch_one(self, suffix: str, parameters: tuple[Any, ...] = ()) -> IngestionJob | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, source_url, status, documents_discovered,
                           documents_processed, chunks_created, error_message,
                           created_at, started_at, completed_at
                    FROM ingestion_jobs
                    {suffix}
                    """,
                    parameters,
                )
                row = cursor.fetchone()
        return self._from_row(row) if row is not None else None

    @staticmethod
    def _parameters(job: IngestionJob) -> tuple[Any, ...]:
        return (
            str(job.id),
            job.source_url,
            job.status.value,
            job.documents_discovered,
            job.documents_processed,
            job.chunks_created,
            job.error_message,
            job.created_at,
            job.started_at,
            job.completed_at,
        )

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> IngestionJob:
        return IngestionJob(
            id=UUID(str(row[0])),
            source_url=row[1],
            status=IngestionStatus(row[2]),
            documents_discovered=row[3],
            documents_processed=row[4],
            chunks_created=row[5],
            error_message=row[6],
            created_at=row[7],
            started_at=row[8],
            completed_at=row[9],
        )
