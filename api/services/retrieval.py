from api.services.embeddings import cosine_similarity, get_embedding

DOCUMENTS = []
CHUNKS = []


def search_chunks(query: str, limit: int = 3):
    query_embedding = get_embedding(query)
    results = []

    for chunk in CHUNKS:
        score = cosine_similarity(query_embedding, chunk["embedding"])
        results.append((score, chunk))

    results.sort(key=lambda x: x[0], reverse=True)

    return [chunk for _, chunk in results[:limit]]
