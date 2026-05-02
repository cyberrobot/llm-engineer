from api.services.embeddings import get_embedding
from api.services.settings import CHUNKS_MAX_DISTANCE, CHUNKS_SEARCH_RESULTS_LIMIT
from api.services.storage import search_chunks_by_embedding


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
