from api.services.retrieval import deduplicate, multi_query_search


def rag_search(query: str, user_role: str):
    results = multi_query_search(query, user_role)
    results = deduplicate(results)
    return results
