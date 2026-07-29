from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from assistant.application.chat import ChatService
from assistant.application.prompt_builder import PromptBuilder
from assistant.application.retrieval_service import RetrievalService
from assistant.infrastructure.repositories import KnowledgeRepository, VectorKnowledgeRepository
from assistant.infrastructure.seed_knowledge import SEED_VECTOR_ENTRIES
from assistant.infrastructure.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from core.config import DATABASE_URL
from infrastructure.ai import AIProvider, create_ai_provider


@lru_cache
def get_ai_provider() -> AIProvider:
    """Provide the configured AI adapter at the application boundary."""
    return create_ai_provider()


@lru_cache
def get_vector_store() -> VectorStore:
    """Use pgvector when configured and deterministic seed knowledge otherwise."""
    if DATABASE_URL:
        return PgVectorStore()
    return InMemoryVectorStore(SEED_VECTOR_ENTRIES)


def get_knowledge_repository(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> KnowledgeRepository:
    return VectorKnowledgeRepository(vector_store)


def get_retrieval_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    repository: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
) -> RetrievalService:
    return RetrievalService(ai_provider, repository)


def get_chat_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> ChatService:
    """Provide the application service used by Assistant chat routes."""
    return ChatService(ai_provider, retrieval_service, PromptBuilder())
