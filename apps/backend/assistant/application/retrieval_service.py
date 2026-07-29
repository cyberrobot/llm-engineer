from assistant.domain import KnowledgeChunk
from assistant.infrastructure.repositories import KnowledgeRepository
from infrastructure.ai.providers import AIProvider


class RetrievalService:
    """Embed a query and retrieve ranked knowledge without generating text."""

    def __init__(
        self,
        embedding_provider: AIProvider,
        knowledge_repository: KnowledgeRepository,
        *,
        limit: int = 3,
        min_score: float = 0.7,
    ) -> None:
        if limit < 1:
            raise ValueError("Retrieval limit must be at least one")
        if not -1 <= min_score <= 1:
            raise ValueError("Minimum similarity score must be between -1 and 1")
        self._embedding_provider = embedding_provider
        self._knowledge_repository = knowledge_repository
        self._limit = limit
        self._min_score = min_score

    def retrieve(self, query: str) -> list[KnowledgeChunk]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        embedding = self._embedding_provider.generate_embedding(text=normalized_query)
        if not embedding:
            return []
        return self._knowledge_repository.find_relevant_chunks(
            embedding,
            limit=self._limit,
            min_score=self._min_score,
        )
