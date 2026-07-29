import json
from collections.abc import Callable
from typing import Any, Literal, cast

from assistant.domain.knowledge_persistence import (
    KnowledgeDocumentRecord,
    KnowledgePersistenceRepository,
    KnowledgeWriteResult,
    PersistedKnowledgeChunk,
)
from infrastructure.database.connection import get_connection


class PostgresKnowledgePersistenceRepository(KnowledgePersistenceRepository):
    """Persist website knowledge into the tables already queried by retrieval."""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def find_document_by_source_url(self, source_url: str) -> KnowledgeDocumentRecord | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_url, title, content_hash, access_roles
                    FROM documents
                    WHERE source_url = %s
                    """,
                    (source_url,),
                )
                row = cursor.fetchone()
        return self._map_document(row) if row else None

    def replace_document(
        self,
        document: KnowledgeDocumentRecord,
        chunks: list[PersistedKnowledgeChunk],
    ) -> KnowledgeWriteResult:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                # Serialize writers for one source URL without introducing external locks.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (document.source_url,)
                )
                cursor.execute(
                    """
                    SELECT id, source_url, title, content_hash, access_roles,
                           (SELECT count(*) FROM chunks WHERE doc_id = documents.id)
                    FROM documents
                    WHERE source_url = %s
                    FOR UPDATE
                    """,
                    (document.source_url,),
                )
                row = cursor.fetchone()
                previous_count = int(row[5]) if row else 0
                if row and str(row[3]) == document.content_hash:
                    return KnowledgeWriteResult(
                        action="unchanged",
                        document_id=str(row[0]),
                        previous_chunk_count=previous_count,
                    )

                action: Literal["created", "updated"] = "updated" if row else "created"
                if row:
                    document_id = str(row[0])
                    cursor.execute(
                        """
                        UPDATE documents
                        SET title = %s,
                            content_hash = %s,
                            access_roles = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            document.title,
                            document.content_hash,
                            json.dumps(document.access_roles),
                            document_id,
                        ),
                    )
                    cursor.execute("DELETE FROM chunks WHERE doc_id = %s", (document_id,))
                else:
                    document_id = document.id
                    cursor.execute(
                        """
                        INSERT INTO documents (
                            id, doc_type, access_roles, status, source_url, title, content_hash
                        )
                        VALUES (%s, 'website', %s, 'indexed', %s, %s, %s)
                        """,
                        (
                            document_id,
                            json.dumps(document.access_roles),
                            document.source_url,
                            document.title,
                            document.content_hash,
                        ),
                    )

                cursor.executemany(
                    """
                    INSERT INTO chunks (
                        id, doc_id, text, embedding, access_roles,
                        sequence, content_hash, heading_path
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (document.source_url,),
                )
                cursor.execute(
                    """
                    SELECT id, content_hash,
                           (SELECT count(*) FROM chunks WHERE doc_id = documents.id)
                    FROM documents
                    WHERE source_url = %s
                    FOR UPDATE
                    """,
                    (document.source_url,),
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
                    WHERE id = %s
                    """,
                    (document.title, json.dumps(document.access_roles), document_id),
                )
                cursor.execute(
                    """
                    UPDATE chunks
                    SET access_roles = %s, updated_at = NOW()
                    WHERE doc_id = %s
                    """,
                    (json.dumps(document.access_roles), document_id),
                )
        return KnowledgeWriteResult(
            action="updated",
            document_id=document_id,
            previous_chunk_count=chunk_count,
        )

    @staticmethod
    def _map_document(row: Any) -> KnowledgeDocumentRecord:
        roles = cast(list[str], row[4])
        return KnowledgeDocumentRecord(
            id=str(row[0]),
            source_url=str(row[1]),
            title=str(row[2]) if row[2] is not None else None,
            content_hash=str(row[3]),
            access_roles=tuple(roles),
        )


__all__ = [
    "KnowledgeDocumentRecord",
    "KnowledgeWriteResult",
    "PersistedKnowledgeChunk",
    "PostgresKnowledgePersistenceRepository",
]
