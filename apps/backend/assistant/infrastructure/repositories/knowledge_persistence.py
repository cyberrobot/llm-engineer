import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Literal, cast
from uuid import UUID

from assistant.domain.assistant import DocumentRetrievalState
from assistant.domain.knowledge_persistence import (
    CommittedIngestionResult,
    KnowledgeDocumentRecord,
    KnowledgePersistenceRepository,
    KnowledgePersistenceResult,
    KnowledgePersistenceTransaction,
    KnowledgePersistenceWriteConflict,
    KnowledgeWriteResult,
    PersistedKnowledgeChunk,
    PersistIngestionResult,
)
from infrastructure.database.connection import get_connection


class PostgresKnowledgePersistenceRepository(KnowledgePersistenceRepository):
    """Persist website knowledge into the tables already queried by retrieval."""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def find_document_by_source_url(
        self, source_url: str, *, assistant_id: UUID
    ) -> KnowledgeDocumentRecord | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_url, title, content_hash, access_roles,
                           assistant_id, retrieval_state
                    FROM documents
                    WHERE source_url = %s AND assistant_id = %s
                    """,
                    (source_url, str(assistant_id)),
                )
                row = cursor.fetchone()
        return self._map_document(row) if row else None

    @contextmanager
    def transaction(self) -> Iterator[KnowledgePersistenceTransaction]:
        """Yield one transaction-scoped writer; exit commits and exceptions roll back."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                yield PostgresKnowledgePersistenceTransaction(cursor)

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
        *,
        ingestion_job_id: UUID | None = None,
        expected_previous_content_hash: str | None = None,
        force_replace: bool = False,
    ) -> KnowledgeWriteResult:
        with self.transaction() as transaction:
            return transaction.replace_document(
                document,
                chunks,
                ingestion_job_id=ingestion_job_id,
                expected_previous_content_hash=expected_previous_content_hash,
                force_replace=force_replace,
            )

    def update_document_metadata(
        self,
        document: KnowledgeDocumentRecord,
    ) -> KnowledgeWriteResult:
        with self.transaction() as transaction:
            return transaction.update_document_metadata(document)

    @staticmethod
    def _map_document(row: Any) -> KnowledgeDocumentRecord:
        roles = cast(list[str], row[4])
        return KnowledgeDocumentRecord(
            id=str(row[0]),
            assistant_id=UUID(str(row[5])),
            source_url=str(row[1]),
            title=str(row[2]) if row[2] is not None else None,
            content_hash=str(row[3]),
            access_roles=tuple(roles),
            retrieval_state=DocumentRetrievalState(row[6]),
        )


class PostgresKnowledgePersistenceTransaction(KnowledgePersistenceTransaction):
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def lock_ingestion_job(self, ingestion_job_id: UUID, document_id: str) -> None:
        self._cursor.execute(
            "SELECT document_id FROM document_ingestion_jobs WHERE id = %s FOR UPDATE",
            (str(ingestion_job_id),),
        )
        row = self._cursor.fetchone()
        if row is None or str(row[0]) != document_id:
            raise ValueError("Ingestion job does not belong to the persistence document.")

    def find_committed_result(self, ingestion_job_id: UUID) -> CommittedIngestionResult | None:
        self._cursor.execute(
            """
            SELECT document_id, command_hash, result
            FROM ingestion_persistence_results
            WHERE ingestion_job_id = %s
            """,
            (str(ingestion_job_id),),
        )
        row = self._cursor.fetchone()
        if row is None:
            return None
        values = row[2]
        return CommittedIngestionResult(
            ingestion_job_id,
            str(row[0]),
            str(row[1]),
            KnowledgePersistenceResult(**values),
        )

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
        *,
        ingestion_job_id: UUID | None = None,
        expected_previous_content_hash: str | None = None,
        force_replace: bool = False,
    ) -> KnowledgeWriteResult:
        cursor = self._cursor
        # Serialize writers for one source URL without holding locks during embedding generation.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{document.assistant_id}:{document.source_url}",),
        )
        cursor.execute(
            """
                    SELECT id, source_url, title, content_hash, access_roles,
                           (SELECT count(*) FROM chunks WHERE doc_id = documents.id)
                    FROM documents
                    WHERE source_url = %s AND assistant_id = %s
                    FOR UPDATE
                    """,
            (document.source_url, str(document.assistant_id)),
        )
        row = cursor.fetchone()
        previous_count = int(row[5]) if row else 0
        current_hash = str(row[3]) if row and row[3] is not None else None
        if (
            row
            and expected_previous_content_hash is not None
            and expected_previous_content_hash != current_hash
        ):
            raise KnowledgePersistenceWriteConflict(
                "The active document changed after replacement preparation."
            )
        if row and current_hash == document.content_hash and not force_replace:
            return KnowledgeWriteResult(
                action="unchanged",
                document_id=str(row[0]),
                previous_chunk_count=previous_count,
            )

        action: Literal["created", "updated"] = "updated" if row else "created"
        job_id = str(ingestion_job_id) if ingestion_job_id else None
        if row:
            document_id = str(row[0])
            cursor.execute(
                """
                        UPDATE documents
                        SET title = %s,
                            content_hash = %s,
                            access_roles = %s,
                            last_ingestion_job_id = %s,
                            updated_at = NOW()
                        WHERE id = %s AND assistant_id = %s
                        """,
                (
                    document.title,
                    document.content_hash,
                    json.dumps(document.access_roles),
                    job_id,
                    document_id,
                    str(document.assistant_id),
                ),
            )
            cursor.execute("DELETE FROM chunks WHERE doc_id = %s", (document_id,))
        else:
            document_id = document.id
            cursor.execute(
                """
                        INSERT INTO documents (
                            id, doc_type, access_roles, status, source_url, title, content_hash,
                            last_ingestion_job_id, assistant_id, retrieval_state
                        )
                        VALUES (%s, 'website', %s, 'indexed', %s, %s, %s, %s, %s, %s)
                        """,
                (
                    document_id,
                    json.dumps(document.access_roles),
                    document.source_url,
                    document.title,
                    document.content_hash,
                    job_id,
                    str(document.assistant_id),
                    document.retrieval_state.value,
                ),
            )

        cursor.executemany(
            """
                    INSERT INTO chunks (
                        id, doc_id, text, embedding, access_roles,
                        sequence, content_hash, heading_path, ingestion_job_id, assistant_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
            [
                (
                    item.id,
                    document_id,
                    item.text,
                    list(item.embedding),
                    json.dumps(item.access_roles),
                    item.sequence,
                    item.content_hash,
                    json.dumps(item.heading_path),
                    job_id,
                    str(item.assistant_id),
                )
                for item in chunks
            ],
        )
        return KnowledgeWriteResult(
            action=action,
            document_id=document_id,
            previous_chunk_count=previous_count,
        )

    def update_document_metadata(
        self,
        document: KnowledgeDocumentRecord,
    ) -> KnowledgeWriteResult:
        cursor = self._cursor
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{document.assistant_id}:{document.source_url}",),
        )
        cursor.execute(
            """
                    SELECT id, content_hash,
                           (SELECT count(*) FROM chunks WHERE doc_id = documents.id)
                    FROM documents
                    WHERE source_url = %s AND assistant_id = %s
                    FOR UPDATE
                    """,
            (document.source_url, str(document.assistant_id)),
        )
        row = cursor.fetchone()
        if not row or str(row[1]) != document.content_hash:
            raise RuntimeError("Knowledge changed during its metadata update.")
        document_id = str(row[0])
        chunk_count = int(row[2])
        cursor.execute(
            """
                    UPDATE documents
                    SET title = %s, access_roles = %s, updated_at = NOW()
                    WHERE id = %s AND assistant_id = %s
                    """,
            (
                document.title,
                json.dumps(document.access_roles),
                document_id,
                str(document.assistant_id),
            ),
        )
        cursor.execute(
            """
                    UPDATE chunks
                    SET access_roles = %s, updated_at = NOW()
                    WHERE doc_id = %s AND assistant_id = %s
                    """,
            (json.dumps(document.access_roles), document_id, str(document.assistant_id)),
        )
        return KnowledgeWriteResult(
            action="updated",
            document_id=document_id,
            previous_chunk_count=chunk_count,
        )

    def record_committed_result(
        self, command: PersistIngestionResult, result: KnowledgePersistenceResult
    ) -> None:
        self._cursor.execute(
            """
            INSERT INTO ingestion_persistence_results (
                ingestion_job_id, document_id, command_hash, persistence_mode,
                source_fingerprint, result
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                str(command.ingestion_job_id),
                command.document_id,
                command.command_hash,
                command.mode.value,
                command.source_fingerprint,
                json.dumps(asdict(result)),
            ),
        )


__all__ = [
    "KnowledgeDocumentRecord",
    "KnowledgeWriteResult",
    "PersistedKnowledgeChunk",
    "PostgresKnowledgePersistenceRepository",
]
