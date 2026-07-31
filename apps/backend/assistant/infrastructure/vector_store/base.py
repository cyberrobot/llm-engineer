from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """Storage-neutral result returned by similarity search."""

    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float
    source_uri: str | None = None


class VectorStore(ABC):
    """Replaceable vector similarity search boundary."""

    @abstractmethod
    def similarity_search(
        self,
        embedding: list[float],
        *,
        assistant_id: UUID,
        limit: int,
        min_score: float,
    ) -> list[VectorRecord]:
        """Return the most similar records in descending score order."""
