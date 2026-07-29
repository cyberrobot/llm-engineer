"""Adapters from stable retrieval-domain values to evaluation records."""

from collections.abc import Sequence

from pydantic import JsonValue

from assistant.domain import KnowledgeChunk
from assistant.evaluation.models import RetrievedItem


def to_evaluation_retrieved_items(results: Sequence[KnowledgeChunk]) -> list[RetrievedItem]:
    """Preserve production retrieval order while assigning one-based evaluation ranks."""

    adapted: list[RetrievedItem] = []
    for rank, chunk in enumerate(results, start=1):
        metadata: dict[str, JsonValue] = {"document_title": chunk.document.title}
        if chunk.document.source_uri is not None:
            metadata["source_uri"] = chunk.document.source_uri
        adapted.append(
            RetrievedItem(
                id=str(chunk.id),
                rank=rank,
                document_id=chunk.document.id,
                chunk_id=str(chunk.id),
                content=chunk.content,
                score=chunk.score,
                metadata=metadata,
            )
        )
    return adapted
