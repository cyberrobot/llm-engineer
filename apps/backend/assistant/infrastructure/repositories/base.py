from abc import ABC, abstractmethod

from assistant.domain import KnowledgeChunk


class KnowledgeRepository(ABC):
    """Application-facing access to stored knowledge."""

    @abstractmethod
    def find_relevant_chunks(
        self,
        query_embedding: list[float],
        *,
        limit: int,
        min_score: float,
    ) -> list[KnowledgeChunk]:
        """Return ranked chunks relevant to a query embedding."""
