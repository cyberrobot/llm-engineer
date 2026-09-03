from uuid import UUID

from assistant.application.ports.rag_knowledge_repository import RagKnowledgeChunk
from core.config import WEIGHT_EMBEDDING_SIMILARITY, WEIGHT_KEYWORD_MATCH
from infrastructure.database.connection import get_connection

VECTOR_CANDIDATE_LIMIT = 50


class PostgresRagKnowledgeRepository:
    """PostgreSQL-backed, read-only persistence boundary for legacy RAG retrieval."""

    def __init__(
        self,
        connection_factory=get_connection,
        *,
        weight_keyword_match: float = WEIGHT_KEYWORD_MATCH,
        weight_embedding_similarity: float = WEIGHT_EMBEDDING_SIMILARITY,
    ) -> None:
        self._connection_factory = connection_factory
        self._weight_keyword_match = weight_keyword_match
        self._weight_embedding_similarity = weight_embedding_similarity

    def search(
        self,
        *,
        assistant_id: UUID,
        query_embedding: list[float],
        query: str,
        access_role: str,
        limit: int,
    ) -> list[RagKnowledgeChunk]:
        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                WITH vector_candidates AS (
                  SELECT chunks.id, chunks.doc_id, chunks.text,
                         chunks.embedding <=> %s::vector AS distance,
                         chunks.access_roles, chunks.text_search
                  FROM chunks
                  JOIN documents ON documents.id = chunks.doc_id
                  WHERE chunks.assistant_id = %s
                    AND documents.assistant_id = %s
                    AND documents.retrieval_state = 'enabled'
                    AND chunks.access_roles ? %s
                  ORDER BY chunks.embedding <=> %s::vector
                  LIMIT %s
                )
                SELECT id, doc_id, text, distance, access_roles,
                       ts_rank(text_search, plainto_tsquery('english', %s)) AS keyword_match,
                       ((1 - distance) * %s
                         + ts_rank(text_search, plainto_tsquery('english', %s)) * %s
                       ) AS hybrid_score
                FROM vector_candidates
                ORDER BY hybrid_score DESC
                LIMIT %s
                """,
                (
                    query_embedding,
                    str(assistant_id),
                    str(assistant_id),
                    access_role,
                    query_embedding,
                    VECTOR_CANDIDATE_LIMIT,
                    query,
                    self._weight_embedding_similarity,
                    query,
                    self._weight_keyword_match,
                    limit,
                ),
            ).fetchall()

        return [
            RagKnowledgeChunk(
                id=row[0],
                doc_id=row[1],
                text=row[2],
                distance=float(row[3]),
                access_roles=row[4],
                keyword_match=float(row[5]),
                hybrid_score=float(row[6]),
            )
            for row in rows
        ]
