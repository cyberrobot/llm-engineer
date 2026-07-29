from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from assistant.application.chat import ChatService
from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.ingestion_service import IngestionService
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.ports.content_extractor import ContentExtractor
from assistant.application.ports.text_chunker import TextChunker
from assistant.application.ports.text_cleaner import TextCleaner
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.application.prompt_builder import PromptBuilder
from assistant.application.retrieval_service import RetrievalService
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader
from assistant.infrastructure.repositories import (
    IngestionJobRepository,
    InMemoryIngestionJobRepository,
    KnowledgeRepository,
    PostgresIngestionJobRepository,
    PostgresKnowledgePersistenceRepository,
    VectorKnowledgeRepository,
)
from assistant.infrastructure.seed_knowledge import SEED_VECTOR_ENTRIES
from assistant.infrastructure.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from core.config import (
    DATABASE_URL,
    get_content_processing_settings,
    get_knowledge_persistence_settings,
    get_website_loader_settings,
)
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


@lru_cache
def get_ingestion_job_repository() -> IngestionJobRepository:
    if DATABASE_URL:
        return PostgresIngestionJobRepository()
    return InMemoryIngestionJobRepository()


@lru_cache
def get_website_loader() -> WebsiteLoader:
    settings = get_website_loader_settings()
    return HttpWebsiteLoader(
        timeout_seconds=settings.timeout_seconds,
        user_agent=settings.user_agent,
        max_pages=settings.max_pages,
        max_response_size=settings.max_response_size,
        max_retries=settings.max_retries,
    )


@lru_cache
def get_content_extractor() -> ContentExtractor:
    return HtmlContentExtractor()


@lru_cache
def get_text_cleaner() -> TextCleaner:
    settings = get_content_processing_settings()
    return NormalisingTextCleaner(min_document_length=settings.min_document_length_characters)


@lru_cache
def get_text_chunker() -> TextChunker:
    settings = get_content_processing_settings()
    return SemanticTextChunker(
        chunk_size=settings.chunk_size_characters,
        overlap=settings.chunk_overlap_characters,
        min_chunk_size=settings.min_chunk_size_characters,
    )


def get_content_processing_service(
    extractor: Annotated[ContentExtractor, Depends(get_content_extractor)],
    cleaner: Annotated[TextCleaner, Depends(get_text_cleaner)],
    chunker: Annotated[TextChunker, Depends(get_text_chunker)],
) -> ContentProcessingService:
    return ContentProcessingService(extractor, cleaner, chunker)


@lru_cache
def get_knowledge_persistence_repository() -> PostgresKnowledgePersistenceRepository:
    return PostgresKnowledgePersistenceRepository()


def get_knowledge_persistence_service(
    embedding_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    repository: Annotated[
        PostgresKnowledgePersistenceRepository,
        Depends(get_knowledge_persistence_repository),
    ],
) -> KnowledgePersistenceService:
    settings = get_knowledge_persistence_settings()
    return KnowledgePersistenceService(
        embedding_provider,
        repository,
        embedding_dimensions=settings.embedding_dimensions,
        embedding_batch_size=settings.embedding_batch_size,
    )


def get_ingestion_service(
    repository: Annotated[IngestionJobRepository, Depends(get_ingestion_job_repository)],
    website_loader: Annotated[WebsiteLoader, Depends(get_website_loader)],
    content_processing_service: Annotated[
        ContentProcessingService, Depends(get_content_processing_service)
    ],
    knowledge_persistence_service: Annotated[
        KnowledgePersistenceService, Depends(get_knowledge_persistence_service)
    ],
) -> IngestionService:
    return IngestionService(
        repository,
        website_loader,
        content_processing_service,
        knowledge_persistence_service,
    )
