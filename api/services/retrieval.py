from api.services.embeddings import cosine_similarity, get_embedding
from api.services.settings import CHUNKS_SEARCH_RESULTS_LIMIT, CHUNKS_SIMILARITY_THRESHOLD

DOCUMENTS = []
CHUNKS = []


def search_chunks(
    query: str,
    limit: int = CHUNKS_SEARCH_RESULTS_LIMIT,
    threshold: float = CHUNKS_SIMILARITY_THRESHOLD,
):
    query_embedding = get_embedding(query)
    results = []

    for chunk in CHUNKS:
        score = cosine_similarity(query_embedding, chunk["embedding"])

        if score >= threshold:
            results.append((score, chunk))

    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[:limit]

    if not top_results or top_results[0][0] < threshold:
        return []

    return top_results
