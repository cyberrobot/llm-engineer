import math
from dataclasses import dataclass

from assistant.infrastructure.vector_store.base import VectorRecord, VectorStore


@dataclass(frozen=True, slots=True)
class InMemoryVectorEntry:
    record: VectorRecord
    embedding: tuple[float, ...]


class InMemoryVectorStore(VectorStore):
    """Small deterministic vector store for fixtures and local seed knowledge."""

    def __init__(self, entries: tuple[InMemoryVectorEntry, ...] = ()) -> None:
        self._entries = entries

    def similarity_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        min_score: float,
    ) -> list[VectorRecord]:
        ranked: list[VectorRecord] = []
        for entry in self._entries:
            score = self._cosine_similarity(embedding, entry.embedding)
            if score >= min_score:
                ranked.append(
                    VectorRecord(
                        chunk_id=entry.record.chunk_id,
                        document_id=entry.record.document_id,
                        document_title=entry.record.document_title,
                        content=entry.record.content,
                        score=score,
                        source_uri=entry.record.source_uri,
                    )
                )
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]

    @staticmethod
    def _cosine_similarity(left: list[float], right: tuple[float, ...]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
