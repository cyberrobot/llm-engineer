from uuid import UUID

from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.infrastructure.repositories.base import KnowledgeRepository
from assistant.infrastructure.vector_store import VectorStore


class VectorKnowledgeRepository(KnowledgeRepository):
    """Map vector-store records into knowledge domain models."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def find_relevant_chunks(
        self,
        query_embedding: list[float],
        *,
        assistant_id: UUID,
        limit: int,
        min_score: float,
    ) -> list[KnowledgeChunk]:
        records = self._vector_store.similarity_search(
            query_embedding,
            assistant_id=assistant_id,
            limit=limit,
            min_score=min_score,
        )
        return [
            KnowledgeChunk(
                id=record.chunk_id,
                document=KnowledgeDocument(
                    id=record.document_id,
                    title=record.document_title,
                    source_uri=record.source_uri,
                ),
                content=record.content,
                score=record.score,
            )
            for record in records
        ]
