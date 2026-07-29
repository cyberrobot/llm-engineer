from collections.abc import Callable
from typing import Any

from assistant.infrastructure.vector_store.base import VectorRecord, VectorStore
from infrastructure.database.connection import get_connection


class PgVectorStore(VectorStore):
    """pgvector-backed cosine similarity search adapter."""

    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def similarity_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        min_score: float,
    ) -> list[VectorRecord]:
        if not embedding:
            return []
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        chunks.id,
                        documents.id,
                        COALESCE(documents.original_filename, documents.doc_type),
                        chunks.text,
                        1 - (chunks.embedding <=> %s::vector) AS score,
                        documents.upload_path
                    FROM chunks
                    JOIN documents ON documents.id = chunks.doc_id
                    WHERE 1 - (chunks.embedding <=> %s::vector) >= %s
                    ORDER BY chunks.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, embedding, min_score, embedding, limit),
                )
                rows = cursor.fetchall()

        return [
            VectorRecord(
                chunk_id=str(row[0]),
                document_id=str(row[1]),
                document_title=str(row[2]),
                content=str(row[3]),
                score=float(row[4]),
                source_uri=str(row[5]) if row[5] else None,
            )
            for row in rows
        ]
