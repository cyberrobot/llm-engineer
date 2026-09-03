from uuid import UUID

from assistant.application.ports.rag_knowledge_repository import RagKnowledgeRepository
from assistant.application.retrieval import deduplicate, multi_query_search


def rag_search(
    assistant_id: UUID,
    query: str,
    user_role: str,
    repository: RagKnowledgeRepository,
):
    output = multi_query_search(assistant_id, query, user_role, repository)
    results = output["results"]
    multi_query = output["multi_query"]
    results = deduplicate(results)
    return {"results": results, "multi_query": multi_query}
