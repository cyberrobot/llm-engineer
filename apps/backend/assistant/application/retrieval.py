from assistant.infrastructure.generate_queries import generate_queries_cached
from assistant.infrastructure.storage import search_chunks_by_embedding
from core.config import CHUNKS_MAX_DISTANCE, CHUNKS_SEARCH_RESULTS_LIMIT
from infrastructure.ai.embeddings import get_embedding


def search_chunks(
    query: str,
    user_role: str,
    limit: int = CHUNKS_SEARCH_RESULTS_LIMIT,
    max_distance: float = CHUNKS_MAX_DISTANCE,
):
    query_embedding = get_embedding(query)
    top_results = search_chunks_by_embedding(query_embedding, query, user_role, limit)

    if not top_results or top_results[0]["distance"] > max_distance:
        return []

    return top_results


def multi_query_search(query: str, user_role: str):
    queries = generate_queries_cached(query)

    all_results = []

    for q in queries:
        results = search_chunks(q, user_role)
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
