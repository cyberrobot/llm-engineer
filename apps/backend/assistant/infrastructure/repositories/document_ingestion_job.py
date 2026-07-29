from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import UUID

import psycopg

from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from infrastructure.database.connection import get_connection


class DocumentRecordNotFound(LookupError):
    pass


class IngestionJobRepositoryFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionJobPage:
    items: list[DocumentIngestionJob]
    total: int


@dataclass(frozen=True)
class IngestionDocumentSource:
    source_url: str
    access_roles: tuple[str, ...]


class DocumentIngestionJobRepository(ABC):
    @abstractmethod
    def document_exists(self, document_id: str) -> bool: ...

    @abstractmethod
    def get_document_source(self, document_id: str) -> IngestionDocumentSource | None: ...

    @abstractmethod
    def create(self, job: DocumentIngestionJob) -> DocumentIngestionJob: ...

    @abstractmethod
    def update(self, job: DocumentIngestionJob) -> None: ...

    @abstractmethod
    def get_by_id(self, job_id: UUID) -> DocumentIngestionJob | None: ...

    @abstractmethod
    def get_by_idempotency_key(self, key: str) -> DocumentIngestionJob | None: ...

    @abstractmethod
    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
        document_id: str | None = None,
    ) -> IngestionJobPage: ...


class InMemoryDocumentIngestionJobRepository(DocumentIngestionJobRepository):
    def __init__(
        self,
        *,
        document_ids: set[str] | None = None,
        document_sources: Mapping[str, IngestionDocumentSource] | None = None,
    ) -> None:
        self._document_sources = dict(document_sources or {})
        self._document_ids = set(document_ids or ()) | set(self._document_sources)
        self._jobs: dict[UUID, DocumentIngestionJob] = {}
        self._idempotency: dict[str, UUID] = {}
        self._lock = RLock()

    def document_exists(self, document_id: str) -> bool:
        return document_id in self._document_ids

    def get_document_source(self, document_id: str) -> IngestionDocumentSource | None:
        return self._document_sources.get(document_id)

    def create(self, job: DocumentIngestionJob) -> DocumentIngestionJob:
        with self._lock:
            if job.document_id not in self._document_ids:
                raise DocumentRecordNotFound(job.document_id)
            if job.idempotency_key is not None and job.idempotency_key in self._idempotency:
                return deepcopy(self._jobs[self._idempotency[job.idempotency_key]])
            if job.id in self._jobs:
                raise IngestionJobRepositoryFailure("Ingestion job identifier already exists.")
            self._jobs[job.id] = deepcopy(job)
            if job.idempotency_key is not None:
                self._idempotency[job.idempotency_key] = job.id
            return deepcopy(job)

    def get_by_id(self, job_id: UUID) -> DocumentIngestionJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def update(self, job: DocumentIngestionJob) -> None:
        with self._lock:
            if job.id not in self._jobs:
                raise IngestionJobRepositoryFailure("Ingestion job does not exist.")
            self._jobs[job.id] = deepcopy(job)

    def get_by_idempotency_key(self, key: str) -> DocumentIngestionJob | None:
        with self._lock:
            job_id = self._idempotency.get(key)
            return deepcopy(self._jobs[job_id]) if job_id is not None else None

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
        document_id: str | None = None,
    ) -> IngestionJobPage:
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if (status is None or job.status is status)
                and (document_id is None or job.document_id == document_id)
            ]
            jobs.sort(key=lambda job: (job.created_at, str(job.id)), reverse=True)
            return IngestionJobPage(items=deepcopy(jobs[offset : offset + limit]), total=len(jobs))


class PostgresDocumentIngestionJobRepository(DocumentIngestionJobRepository):
    _columns = """id, document_id, status, current_step, last_completed_step,
                  retry_count, failure_code,
                  failure_message, idempotency_key, created_at, started_at,
                  completed_at, updated_at"""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def document_exists(self, document_id: str) -> bool:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    "SELECT 1 FROM documents WHERE id = %s", (document_id,)
                ).fetchone()
            return row is not None
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Document lookup failed.") from exc

    def get_document_source(self, document_id: str) -> IngestionDocumentSource | None:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    "SELECT source_url, access_roles FROM documents WHERE id = %s",
                    (document_id,),
                ).fetchone()
            if row is None or row[0] is None:
                return None
            return IngestionDocumentSource(str(row[0]), tuple(row[1]))
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Document source lookup failed.") from exc

    def create(self, job: DocumentIngestionJob) -> DocumentIngestionJob:
        try:
            with self._connection_factory() as connection:
                connection.execute(
                    f"""
                    INSERT INTO document_ingestion_jobs ({self._columns})
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    self._parameters(job),
                )
            return job
        except psycopg.errors.ForeignKeyViolation as exc:
            raise DocumentRecordNotFound(job.document_id) from exc
        except psycopg.errors.UniqueViolation as exc:
            if job.idempotency_key is not None:
                existing = self.get_by_idempotency_key(job.idempotency_key)
                if existing is not None:
                    return existing
            raise IngestionJobRepositoryFailure("Ingestion job uniqueness conflict.") from exc
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job creation failed.") from exc

    def get_by_id(self, job_id: UUID) -> DocumentIngestionJob | None:
        return self._fetch_one("WHERE id = %s", (str(job_id),))

    def update(self, job: DocumentIngestionJob) -> None:
        try:
            with self._connection_factory() as connection:
                result = connection.execute(
                    """
                    UPDATE document_ingestion_jobs
                    SET status = %s, current_step = %s, last_completed_step = %s,
                        retry_count = %s,
                        failure_code = %s, failure_message = %s, started_at = %s,
                        completed_at = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        job.status.value,
                        job.current_step.value if job.current_step else None,
                        job.last_completed_step.value if job.last_completed_step else None,
                        job.retry_count,
                        job.failure_code,
                        job.failure_message,
                        job.started_at,
                        job.completed_at,
                        job.updated_at,
                        str(job.id),
                    ),
                )
                if result.rowcount == 0:
                    raise IngestionJobRepositoryFailure("Ingestion job does not exist.")
        except IngestionJobRepositoryFailure:
            raise
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job update failed.") from exc

    def get_by_idempotency_key(self, key: str) -> DocumentIngestionJob | None:
        return self._fetch_one("WHERE idempotency_key = %s", (key,))

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
        document_id: str | None = None,
    ) -> IngestionJobPage:
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            clauses.append("status = %s")
            parameters.append(status.value)
        if document_id is not None:
            clauses.append("document_id = %s")
            parameters.append(document_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self._connection_factory() as connection:
                total = connection.execute(
                    f"SELECT count(*) FROM document_ingestion_jobs {where}", parameters
                ).fetchone()[0]
                rows = connection.execute(
                    f"""
                    SELECT {self._columns} FROM document_ingestion_jobs
                    {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
                    """,
                    (*parameters, limit, offset),
                ).fetchall()
            return IngestionJobPage(items=[self._from_row(row) for row in rows], total=total)
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job listing failed.") from exc

    def _fetch_one(self, suffix: str, parameters: tuple[Any, ...]) -> DocumentIngestionJob | None:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    f"SELECT {self._columns} FROM document_ingestion_jobs {suffix}", parameters
                ).fetchone()
            return self._from_row(row) if row is not None else None
        except psycopg.Error as exc:
            raise IngestionJobRepositoryFailure("Ingestion job lookup failed.") from exc

    @staticmethod
    def _parameters(job: DocumentIngestionJob) -> tuple[Any, ...]:
        return (
            str(job.id),
            job.document_id,
            job.status.value,
            job.current_step.value if job.current_step else None,
            job.last_completed_step.value if job.last_completed_step else None,
            job.retry_count,
            job.failure_code,
            job.failure_message,
            job.idempotency_key,
            job.created_at,
            job.started_at,
            job.completed_at,
            job.updated_at,
        )

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> DocumentIngestionJob:
        return DocumentIngestionJob(
            id=UUID(str(row[0])),
            document_id=row[1],
            status=IngestionStatus(row[2]),
            current_step=IngestionStep(row[3]) if row[3] is not None else None,
            last_completed_step=IngestionStep(row[4]) if row[4] is not None else None,
            retry_count=row[5],
            failure_code=row[6],
            failure_message=row[7],
            idempotency_key=row[8],
            created_at=row[9],
            started_at=row[10],
            completed_at=row[11],
            updated_at=row[12],
        )
