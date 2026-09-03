from typing import Protocol, TypedDict
from uuid import UUID


class RagKnowledgeChunk(TypedDict):
    """Application-owned representation of one legacy RAG retrieval result."""

    id: str
    doc_id: str
    text: str
    distance: float
    access_roles: list[str]
    keyword_match: float
    hybrid_score: float


class RagKnowledgeRepository(Protocol):
    """Read-only access to Assistant- and role-scoped RAG knowledge."""

    def search(
        self,
        *,
        assistant_id: UUID,
        query_embedding: list[float],
        query: str,
        access_role: str,
        limit: int,
    ) -> list[RagKnowledgeChunk]: ...
