from uuid import UUID

from assistant.application.ports.rag_knowledge_repository import (
    RagKnowledgeChunk,
    RagKnowledgeRepository,
)
from assistant.infrastructure.generate_queries import generate_queries_cached
from core.config import CHUNKS_MAX_DISTANCE, CHUNKS_SEARCH_RESULTS_LIMIT
from infrastructure.ai.embeddings import get_embedding


def search_chunks(
    assistant_id: UUID,
    query: str,
    user_role: str,
    repository: RagKnowledgeRepository,
    limit: int = CHUNKS_SEARCH_RESULTS_LIMIT,
    max_distance: float = CHUNKS_MAX_DISTANCE,
) -> list[RagKnowledgeChunk]:
    query_embedding = get_embedding(query)
    top_results = repository.search(
        assistant_id=assistant_id,
        query_embedding=query_embedding,
        query=query,
        access_role=user_role,
        limit=limit,
    )

    if not top_results or top_results[0]["distance"] > max_distance:
        return []

    return top_results


def multi_query_search(
    assistant_id: UUID,
    query: str,
    user_role: str,
    repository: RagKnowledgeRepository,
):
    queries = generate_queries_cached(query)

    all_results = []

    for q in queries:
        results = search_chunks(assistant_id, q, user_role, repository)
        all_results.extend(results)

    return {"results": all_results, "multi_query": queries}


def deduplicate(chunks):
    seen = set()
    unique = []

    for c in chunks:
        if c["id"] not in seen:
            unique.append(c)
            seen.add(c["id"])

    return unique


def filter_chunks_by_source_ids(chunks: list[dict], source_ids: list[str]) -> list[dict]:
    source_id_set = set(source_ids)

    return [chunk for chunk in chunks if chunk["id"] in source_id_set]
