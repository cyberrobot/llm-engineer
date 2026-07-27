from api.services.retrieval import deduplicate, multi_query_search


def rag_search(query: str, user_role: str):
    output = multi_query_search(query, user_role)
    results = output["results"]
    multi_query = output["multi_query"]
    results = deduplicate(results)
    return {"results": results, "multi_query": multi_query}
