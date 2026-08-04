import json
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg

from assistant.application.ports.knowledge_source_repository import (
    KnowledgeSourceConflict,
    KnowledgeSourceTransaction,
)
from assistant.domain.assistant import DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.knowledge_source import KnowledgeSource, KnowledgeSourceType
from infrastructure.database.connection import get_connection


class PostgresKnowledgeSourceRepository:
    def __init__(self, connection_factory=get_connection) -> None:
        self._connection_factory = connection_factory

    @contextmanager
    def transaction(self):
        with self._connection_factory() as connection:
            yield _Transaction(connection)

    def get(self, assistant_id: UUID, source_id: UUID) -> KnowledgeSource | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                f"SELECT {_SOURCE_COLUMNS} FROM knowledge_sources WHERE id = %s AND assistant_id = %s",
                (str(source_id), str(assistant_id)),
            ).fetchone()
        return _source(row) if row else None

    def list(
        self, assistant_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[KnowledgeSource], int]:
        with self._connection_factory() as connection:
            total = connection.execute(
                "SELECT count(*) FROM knowledge_sources WHERE assistant_id = %s",
                (str(assistant_id),),
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT {_SOURCE_COLUMNS} FROM knowledge_sources WHERE assistant_id = %s ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                (str(assistant_id), limit, offset),
            ).fetchall()
        return [_source(row) for row in rows], total

    def latest_job(self, document_id: str) -> DocumentIngestionJob | None:
        return self._job(
            "WHERE document_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (document_id,)
        )

    def active_job(self, document_id: str) -> DocumentIngestionJob | None:
        return self._job(
            "WHERE document_id = %s AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1",
            (document_id,),
        )

    def create_job(self, job: DocumentIngestionJob) -> DocumentIngestionJob:
        with self._connection_factory() as connection:
            _insert_job(connection, job)
        return job

    def find_creation(self, key: str) -> tuple[KnowledgeSource, str] | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                f"SELECT {_SOURCE_COLUMNS}, creation_request_hash "
                "FROM knowledge_sources WHERE creation_idempotency_key = %s",
                (key,),
            ).fetchone()
        return (_source(row[:11]), row[11]) if row else None

    def _job(self, suffix: str, parameters: tuple[Any, ...]) -> DocumentIngestionJob | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                f"SELECT {_JOB_COLUMNS} FROM document_ingestion_jobs {suffix}", parameters
            ).fetchone()
        return _job(row) if row else None


class _Transaction(KnowledgeSourceTransaction):
    def __init__(self, connection) -> None:
        self.connection = connection

    def create(self, source, job, request_hash, idempotency_key):
        try:
            source_uri = source.url or f"urn:redmoor:knowledge-source:{source.id}"
            self.connection.execute(
                """INSERT INTO documents (id, doc_type, access_roles, status, source_url, title, content_hash, assistant_id, retrieval_state) VALUES (%s, %s, %s::jsonb, 'pending', %s, %s, %s, %s, %s)""",
                (
                    source.document_id,
                    source.source_type.value,
                    json.dumps(["user"]),
                    source_uri,
                    source.name,
                    source.content_version,
                    str(source.assistant_id),
                    source.retrieval_state.value,
                ),
            )
            self.connection.execute(
                """INSERT INTO knowledge_sources (id, assistant_id, source_type, name, retrieval_state, direct_text, normalized_url, document_id, content_version, creation_idempotency_key, creation_request_hash, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    str(source.id),
                    str(source.assistant_id),
                    source.source_type.value,
                    source.name,
                    source.retrieval_state.value,
                    source.direct_text,
                    source.url,
                    source.document_id,
                    source.content_version,
                    idempotency_key,
                    request_hash,
                    source.created_at,
                    source.updated_at,
                ),
            )
            _insert_job(self.connection, job)
            return source, job
        except psycopg.errors.UniqueViolation as exc:
            raise KnowledgeSourceConflict from exc

    def update_retrieval_state(self, assistant_id, source_id, state):
        row = self.connection.execute(
            f"""UPDATE knowledge_sources SET retrieval_state=%s, updated_at=CASE WHEN retrieval_state=%s THEN updated_at ELSE NOW() END WHERE id=%s AND assistant_id=%s RETURNING {_SOURCE_COLUMNS}""",
            (state.value, state.value, str(source_id), str(assistant_id)),
        ).fetchone()
        if row is None:
            return None
        self.connection.execute(
            "UPDATE documents SET retrieval_state=%s, updated_at=NOW() WHERE id=%s AND assistant_id=%s",
            (state.value, row[7], str(assistant_id)),
        )
        return _source(row)

    def delete(self, assistant_id, source_id):
        row = self.connection.execute(
            "SELECT document_id FROM knowledge_sources WHERE id=%s AND assistant_id=%s FOR UPDATE",
            (str(source_id), str(assistant_id)),
        ).fetchone()
        if row is None:
            return False
        active = self.connection.execute(
            "SELECT 1 FROM document_ingestion_jobs WHERE document_id=%s AND status IN ('queued','running') LIMIT 1",
            (row[0],),
        ).fetchone()
        if active:
            raise KnowledgeSourceConflict("active_ingestion")
        self.connection.execute(
            "DELETE FROM documents WHERE id=%s AND assistant_id=%s", (row[0], str(assistant_id))
        )
        return True


_SOURCE_COLUMNS = "id, assistant_id, source_type, name, retrieval_state, direct_text, normalized_url, document_id, content_version, created_at, updated_at"
_JOB_COLUMNS = "id, document_id, status, current_step, last_completed_step, retry_count, current_step_attempt_count, last_attempted_at, failure_code, failure_message, idempotency_key, created_at, started_at, completed_at, updated_at"


def _source(row):
    return KnowledgeSource(
        UUID(row[0]),
        UUID(row[1]),
        KnowledgeSourceType(row[2]),
        row[3],
        DocumentRetrievalState(row[4]),
        row[5],
        row[6],
        row[7],
        row[8],
        row[9],
        row[10],
    )


def _job(row):
    return DocumentIngestionJob(
        UUID(row[0]),
        row[1],
        IngestionStatus(row[2]),
        IngestionStep(row[3]) if row[3] else None,
        row[5],
        row[8],
        row[9],
        row[10],
        row[11],
        row[12],
        row[13],
        row[14],
        IngestionStep(row[4]) if row[4] else None,
        row[6],
        row[7],
    )


def _insert_job(connection, job):
    connection.execute(
        """INSERT INTO document_ingestion_jobs (id, document_id, status, current_step, last_completed_step, retry_count, current_step_attempt_count, last_attempted_at, failure_code, failure_message, idempotency_key, created_at, started_at, completed_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            str(job.id),
            job.document_id,
            job.status.value,
            None,
            None,
            0,
            0,
            None,
            None,
            None,
            job.idempotency_key,
            job.created_at,
            None,
            None,
            job.updated_at,
        ),
    )
