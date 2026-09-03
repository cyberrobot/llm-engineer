import os
from collections.abc import Callable
from dataclasses import replace
from functools import lru_cache
from time import sleep
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from assistant.application.assistant_admin_service import AssistantAdministrationService
from assistant.application.assistant_behaviour_service import AssistantBehaviourService
from assistant.application.chat import ChatService
from assistant.application.content_processing_service import ContentProcessingService
from assistant.application.evaluation_admin import EvaluationAdministrationService
from assistant.application.ingestion_job_service import DocumentIngestionJobService
from assistant.application.ingestion_pipeline import (
    IngestionPipelineDefinition,
    IngestionPipelineRunner,
)
from assistant.application.ingestion_pipeline_context import WebsiteIngestionContextFactory
from assistant.application.ingestion_pipeline_steps import (
    ChunkIngestionStep,
    EmbedIngestionStep,
    ParseIngestionStep,
    PersistIngestionStep,
)
from assistant.application.ingestion_retry import (
    IngestionFailureClassifier,
    IngestionRetryPolicy,
)
from assistant.application.ingestion_service import IngestionService
from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.knowledge_source_service import KnowledgeSourceService
from assistant.application.ports.content_extractor import ContentExtractor
from assistant.application.ports.rag_knowledge_repository import RagKnowledgeRepository
from assistant.application.ports.text_chunker import TextChunker
from assistant.application.ports.text_cleaner import TextCleaner
from assistant.application.ports.website_loader import WebsiteLoader
from assistant.application.prompt_builder import PromptBuilder
from assistant.application.public_assistant import PublicAssistantConfigurationService
from assistant.application.public_chat import (
    AssistantPreviewChatService,
    PublicAssistantChatService,
)
from assistant.application.public_chat_protection import (
    AnonymousClientResolver,
    InMemoryConcurrencyLimiter,
    PublicChatProtection,
    PublicChatRateLimiter,
    RedisLockConcurrencyLimiter,
)
from assistant.application.retrieval_service import RetrievalService
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourRepository
from assistant.domain.assistant_repository import AssistantRepository
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.evaluation import EvaluationRunner
from assistant.infrastructure.evaluation_files import FileSystemEvaluationResources
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor
from assistant.infrastructure.ingestion.normalising_text_cleaner import NormalisingTextCleaner
from assistant.infrastructure.ingestion.semantic_text_chunker import SemanticTextChunker
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader
from assistant.infrastructure.repositories import (
    DocumentIngestionJobRepository,
    IngestionJobRepository,
    InMemoryAssistantBehaviourRepository,
    InMemoryAssistantRepository,
    InMemoryDocumentIngestionJobRepository,
    InMemoryIngestionJobRepository,
    KnowledgeRepository,
    PostgresAssistantBehaviourRepository,
    PostgresAssistantRepository,
    PostgresDocumentIngestionJobRepository,
    PostgresIngestionJobRepository,
    PostgresKnowledgePersistenceRepository,
    VectorKnowledgeRepository,
)
from assistant.infrastructure.repositories.ingestion_observability import (
    EmptyIngestionOperationalStatusRepository,
    IngestionOperationalStatusRepository,
    IngestionStepExecutionRepository,
    InMemoryIngestionStepExecutionRepository,
    PostgresIngestionOperationalStatusRepository,
    PostgresIngestionStepExecutionRepository,
)
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from assistant.infrastructure.repositories.rag_knowledge import PostgresRagKnowledgeRepository
from assistant.infrastructure.seed_knowledge import SEED_VECTOR_ENTRIES
from assistant.infrastructure.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from core.config import (
    DATABASE_URL,
    DISABLE_RATE_LIMITS,
    REDIS_URL,
    get_ai_settings,
    get_content_processing_settings,
    get_evaluation_admin_settings,
    get_ingestion_retry_settings,
    get_knowledge_persistence_settings,
    get_public_assistant_chat_settings,
    get_website_loader_settings,
)
from infrastructure.ai import AIProvider, create_ai_provider
from infrastructure.cache.client import redis_client


@lru_cache
def get_ai_provider() -> AIProvider:
    """Provide the configured AI adapter at the application boundary."""
    return create_ai_provider()


@lru_cache
def get_ingestion_ai_provider() -> AIProvider:
    """Let ingestion orchestration own retries instead of nesting SDK attempts."""
    return create_ai_provider(replace(get_ai_settings(), max_retries=0))


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


def get_rag_knowledge_repository() -> RagKnowledgeRepository:
    """Provide the read-only PostgreSQL boundary used by the legacy RAG endpoint."""
    return PostgresRagKnowledgeRepository()


def get_retrieval_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    repository: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
) -> RetrievalService:
    return RetrievalService(ai_provider, repository, assistant_id=REDMOOR_ASSISTANT_ID)


def get_chat_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> ChatService:
    """Provide the application service used by Assistant chat routes."""
    return ChatService(ai_provider, retrieval_service, PromptBuilder())


def get_evaluation_administration_service() -> EvaluationAdministrationService:
    """Build a request-local evaluation coordinator over app-lifetime provider resources."""

    settings = get_evaluation_admin_settings()
    resources = FileSystemEvaluationResources(
        dataset_directory=settings.dataset_directory,
        report_directory=settings.report_directory,
    )

    def runner_factory() -> EvaluationRunner:
        provider = get_ai_provider()
        repository = get_knowledge_repository(get_vector_store())
        retrieval_service = get_retrieval_service(provider, repository)
        answer_service = get_chat_service(provider, retrieval_service)
        return EvaluationRunner(
            retrieval_service=retrieval_service,
            answer_service=answer_service,
        )

    return EvaluationAdministrationService(resources, runner_factory=runner_factory)


@lru_cache
def get_assistant_repository() -> AssistantRepository:
    if DATABASE_URL:
        return PostgresAssistantRepository()
    return InMemoryAssistantRepository()


def get_assistant_administration_service(
    repository: Annotated[AssistantRepository, Depends(get_assistant_repository)],
) -> AssistantAdministrationService:
    return AssistantAdministrationService(repository)


@lru_cache
def get_assistant_behaviour_repository() -> AssistantBehaviourRepository:
    if DATABASE_URL:
        return PostgresAssistantBehaviourRepository()
    return InMemoryAssistantBehaviourRepository(get_assistant_repository())


def get_assistant_behaviour_service(
    repository: Annotated[
        AssistantBehaviourRepository, Depends(get_assistant_behaviour_repository)
    ],
) -> AssistantBehaviourService:
    return AssistantBehaviourService(repository)


def get_public_assistant_configuration_service(
    assistant_repository: Annotated[AssistantRepository, Depends(get_assistant_repository)],
    behaviour_repository: Annotated[
        AssistantBehaviourRepository, Depends(get_assistant_behaviour_repository)
    ],
) -> PublicAssistantConfigurationService:
    return PublicAssistantConfigurationService(assistant_repository, behaviour_repository)


def get_public_chat_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    repository: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
    assistant_repository: Annotated[AssistantRepository, Depends(get_assistant_repository)],
    behaviour_repository: Annotated[
        AssistantBehaviourRepository, Depends(get_assistant_behaviour_repository)
    ],
) -> PublicAssistantChatService:
    settings = get_public_assistant_chat_settings()

    def retrieval_factory(assistant_id: UUID) -> RetrievalService:
        return RetrievalService(
            ai_provider,
            repository,
            assistant_id=assistant_id,
            limit=settings.retrieval_limit,
            min_score=settings.minimum_similarity_score,
        )

    return PublicAssistantChatService(
        assistant_repository,
        retrieval_factory,
        ai_provider,
        PromptBuilder(),
        settings,
        behaviour_repository=behaviour_repository,
    )


def get_assistant_preview_chat_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
    repository: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
    assistant_repository: Annotated[AssistantRepository, Depends(get_assistant_repository)],
    behaviour_repository: Annotated[
        AssistantBehaviourRepository, Depends(get_assistant_behaviour_repository)
    ],
) -> AssistantPreviewChatService:
    settings = get_public_assistant_chat_settings()

    def retrieval_factory(assistant_id: UUID) -> RetrievalService:
        return RetrievalService(
            ai_provider,
            repository,
            assistant_id=assistant_id,
            limit=settings.retrieval_limit,
            min_score=settings.minimum_similarity_score,
        )

    return AssistantPreviewChatService(
        assistant_repository,
        behaviour_repository,
        retrieval_factory,
        ai_provider,
        PromptBuilder(),
        settings,
    )


def get_public_chat_service_factory() -> Callable[[], PublicAssistantChatService]:
    """Delay provider/repository construction until low-cost protections have passed."""

    def build() -> PublicAssistantChatService:
        return get_public_chat_service(
            get_ai_provider(),
            get_knowledge_repository(get_vector_store()),
            get_assistant_repository(),
            get_assistant_behaviour_repository(),
        )

    return build


@lru_cache
def get_public_chat_protection() -> PublicChatProtection:
    """Provide process-local development controls or shared production controls."""
    settings = get_public_assistant_chat_settings()
    resolver = AnonymousClientResolver(
        settings.trusted_proxy_networks,
        hash_secret=settings.client_key_hash_secret,
    )
    environment = os.getenv("APP_ENV", "development").strip().lower()
    concurrency_limiter: InMemoryConcurrencyLimiter | RedisLockConcurrencyLimiter
    if environment in {"production", "staging"}:
        rate_limiter = PublicChatRateLimiter(settings, storage_uri=REDIS_URL)
        concurrency_limiter = RedisLockConcurrencyLimiter(
            redis_client,
            per_client=settings.maximum_concurrent_requests_per_client,
            global_limit=settings.maximum_concurrent_requests_global,
            lease_seconds=settings.request_timeout_seconds + 5,
        )
    else:
        from limits.storage import MemoryStorage

        rate_limiter = PublicChatRateLimiter(settings, storage=MemoryStorage())
        concurrency_limiter = InMemoryConcurrencyLimiter(
            per_client=settings.maximum_concurrent_requests_per_client,
            global_limit=settings.maximum_concurrent_requests_global,
        )
    if DISABLE_RATE_LIMITS and environment not in {"development", "test"}:
        raise ValueError("Public chat rate limiting cannot be disabled outside development/test")
    return PublicChatProtection(settings, resolver, rate_limiter, concurrency_limiter)


@lru_cache
def get_ingestion_job_repository() -> IngestionJobRepository:
    if DATABASE_URL:
        return PostgresIngestionJobRepository()
    return InMemoryIngestionJobRepository()


@lru_cache
def get_document_ingestion_job_repository() -> DocumentIngestionJobRepository:
    if DATABASE_URL:
        return PostgresDocumentIngestionJobRepository()
    return InMemoryDocumentIngestionJobRepository()


def get_document_ingestion_job_service(
    repository: Annotated[
        DocumentIngestionJobRepository, Depends(get_document_ingestion_job_repository)
    ],
) -> DocumentIngestionJobService:
    return DocumentIngestionJobService(repository)


@lru_cache
def get_ingestion_step_execution_repository() -> IngestionStepExecutionRepository:
    if DATABASE_URL:
        return PostgresIngestionStepExecutionRepository()
    return InMemoryIngestionStepExecutionRepository()


@lru_cache
def get_ingestion_operational_status_repository() -> IngestionOperationalStatusRepository:
    if DATABASE_URL:
        return PostgresIngestionOperationalStatusRepository()
    return EmptyIngestionOperationalStatusRepository()


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
    embedding_provider: Annotated[AIProvider, Depends(get_ingestion_ai_provider)],
    repository: Annotated[
        PostgresKnowledgePersistenceRepository,
        Depends(get_knowledge_persistence_repository),
    ],
) -> KnowledgePersistenceService:
    settings = get_knowledge_persistence_settings()
    return KnowledgePersistenceService(
        embedding_provider,
        repository,
        assistant_id=REDMOOR_ASSISTANT_ID,
        embedding_dimensions=settings.embedding_dimensions,
        embedding_batch_size=settings.embedding_batch_size,
    )


@lru_cache
def get_knowledge_source_repository() -> PostgresKnowledgeSourceRepository:
    return PostgresKnowledgeSourceRepository()


def get_knowledge_source_service(
    repository: Annotated[
        PostgresKnowledgeSourceRepository, Depends(get_knowledge_source_repository)
    ],
    assistants: Annotated[AssistantRepository, Depends(get_assistant_repository)],
) -> KnowledgeSourceService:
    return KnowledgeSourceService(repository, assistants)


@lru_cache
def get_ingestion_failure_classifier() -> IngestionFailureClassifier:
    return IngestionFailureClassifier()


@lru_cache
def get_ingestion_retry_policy() -> IngestionRetryPolicy:
    return IngestionRetryPolicy(get_ingestion_retry_settings())


def get_ingestion_retry_sleeper() -> Callable[[float], None]:
    return sleep


def get_ingestion_service(
    repository: Annotated[IngestionJobRepository, Depends(get_ingestion_job_repository)],
    website_loader: Annotated[WebsiteLoader, Depends(get_website_loader)],
    content_processing_service: Annotated[
        ContentProcessingService, Depends(get_content_processing_service)
    ],
    knowledge_persistence_service: Annotated[
        KnowledgePersistenceService, Depends(get_knowledge_persistence_service)
    ],
    classifier: Annotated[IngestionFailureClassifier, Depends(get_ingestion_failure_classifier)],
    retry_policy: Annotated[IngestionRetryPolicy, Depends(get_ingestion_retry_policy)],
    sleeper: Annotated[Callable[[float], None], Depends(get_ingestion_retry_sleeper)],
) -> IngestionService:
    return IngestionService(
        repository,
        website_loader,
        content_processing_service,
        knowledge_persistence_service,
        classifier=classifier,
        retry_policy=retry_policy,
        sleeper=sleeper,
    )


def get_ingestion_pipeline_definition(
    website_loader: Annotated[WebsiteLoader, Depends(get_website_loader)],
    content_processing_service: Annotated[
        ContentProcessingService, Depends(get_content_processing_service)
    ],
    knowledge_persistence_service: Annotated[
        KnowledgePersistenceService, Depends(get_knowledge_persistence_service)
    ],
) -> IngestionPipelineDefinition:
    return IngestionPipelineDefinition(
        (
            ParseIngestionStep(website_loader),
            ChunkIngestionStep(content_processing_service),
            EmbedIngestionStep(knowledge_persistence_service),
            PersistIngestionStep(knowledge_persistence_service),
        ),
        # Website parse/chunk/embed payloads are transient and the remote source may change.
        # Only persistence is therefore a reliable cross-process checkpoint today.
        checkpoint_steps=(IngestionStep.persist,),
    )


def get_ingestion_pipeline_runner(
    repository: Annotated[
        DocumentIngestionJobRepository, Depends(get_document_ingestion_job_repository)
    ],
    definition: Annotated[IngestionPipelineDefinition, Depends(get_ingestion_pipeline_definition)],
    website_loader: Annotated[WebsiteLoader, Depends(get_website_loader)],
    content_processing_service: Annotated[
        ContentProcessingService, Depends(get_content_processing_service)
    ],
    knowledge_persistence_service: Annotated[
        KnowledgePersistenceService, Depends(get_knowledge_persistence_service)
    ],
    classifier: Annotated[IngestionFailureClassifier, Depends(get_ingestion_failure_classifier)],
    retry_policy: Annotated[IngestionRetryPolicy, Depends(get_ingestion_retry_policy)],
    sleeper: Annotated[Callable[[float], None], Depends(get_ingestion_retry_sleeper)],
    step_executions: Annotated[
        IngestionStepExecutionRepository,
        Depends(get_ingestion_step_execution_repository),
    ],
) -> IngestionPipelineRunner:
    return build_ingestion_pipeline_runner(
        repository,
        definition,
        website_loader,
        content_processing_service,
        knowledge_persistence_service,
        classifier,
        retry_policy,
        sleeper,
        step_executions,
    )


def build_ingestion_pipeline_runner(
    repository: DocumentIngestionJobRepository,
    definition: IngestionPipelineDefinition,
    website_loader: WebsiteLoader,
    content_processing_service: ContentProcessingService,
    knowledge_persistence_service: KnowledgePersistenceService,
    classifier: IngestionFailureClassifier,
    retry_policy: IngestionRetryPolicy,
    sleeper: Callable[[float], None],
    step_executions: IngestionStepExecutionRepository | None = None,
) -> IngestionPipelineRunner:
    return IngestionPipelineRunner(
        repository,
        definition,
        context_factory=WebsiteIngestionContextFactory(
            repository,
            website_loader,
            content_processing_service,
            knowledge_persistence_service,
        ),
        classifier=classifier,
        retry_policy=retry_policy,
        sleeper=sleeper,
        step_executions=step_executions,
    )
