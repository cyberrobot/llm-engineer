import os
from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from assistant.api.dependencies import (
    get_assistant_repository,
    get_document_ingestion_job_repository,
    get_ingestion_operational_status_repository,
    get_knowledge_source_repository,
)
from assistant.application.audit import get_audit_logs as get_rag_audit_logs
from assistant.domain.assistant_repository import AssistantRepository
from assistant.infrastructure.repositories.document_ingestion_job import (
    DocumentIngestionJobRepository,
)
from assistant.infrastructure.repositories.ingestion_observability import (
    IngestionOperationalStatusRepository,
)
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from core.config import DATABASE_URL, get_health_check_settings
from infrastructure.cache.client import redis_client
from operations.application.administration import (
    AuditQueryService,
    CacheAdministrationService,
    JobOperationsService,
    MaintenanceService,
    OperationsSummaryService,
    RuntimeStateStore,
)
from operations.domain.administration import HealthOverview
from operations.infrastructure.audit import PostgresOperationsAuditStore
from operations.infrastructure.cache import RedisCacheRegion
from operations.infrastructure.dashboard import (
    AssistantSummaryStore,
    IngestionSummaryStore,
    KnowledgeSourceSummaryStore,
)
from operations.infrastructure.jobs import IngestionJobOperationsStore
from operations.infrastructure.memory import (
    InMemoryAuditStore,
    InMemoryRuntimeStateStore,
)
from operations.infrastructure.runtime import PostgresRuntimeStateStore


@lru_cache
def get_runtime_state_store() -> RuntimeStateStore:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if DATABASE_URL and environment in {"production", "staging"}:
        return PostgresRuntimeStateStore()
    return InMemoryRuntimeStateStore()


@lru_cache
def get_cache_administration_service() -> CacheAdministrationService:
    regions = {}
    if not get_health_check_settings().redis_disabled:
        regions["assistant"] = RedisCacheRegion("assistant", redis_client, key_prefix="rag:")
    return CacheAdministrationService(regions)


@lru_cache
def get_audit_query_service() -> AuditQueryService:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    persistent = DATABASE_URL and environment in {"production", "staging"}
    store = PostgresOperationsAuditStore() if persistent else InMemoryAuditStore()
    return AuditQueryService(store)


def get_rag_audit_reader() -> Callable[[int], list[dict]]:
    """Expose the existing RAG debug history through an authenticated Operations adapter."""

    return get_rag_audit_logs


def get_maintenance_service() -> MaintenanceService:
    return MaintenanceService(get_runtime_state_store())


def get_job_operations_service(
    repository: Annotated[
        DocumentIngestionJobRepository, Depends(get_document_ingestion_job_repository)
    ],
) -> JobOperationsService:
    return JobOperationsService(IngestionJobOperationsStore(repository))


def get_operations_summary_service(
    cache: Annotated[CacheAdministrationService, Depends(get_cache_administration_service)],
    audit: Annotated[AuditQueryService, Depends(get_audit_query_service)],
    maintenance: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    jobs: Annotated[JobOperationsService, Depends(get_job_operations_service)],
    assistants: Annotated[AssistantRepository, Depends(get_assistant_repository)],
    knowledge_sources: Annotated[
        PostgresKnowledgeSourceRepository, Depends(get_knowledge_source_repository)
    ],
    ingestion_status: Annotated[
        IngestionOperationalStatusRepository,
        Depends(get_ingestion_operational_status_repository),
    ],
) -> OperationsSummaryService:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    assistant_summary = AssistantSummaryStore(assistants)
    ingestion_summary = IngestionSummaryStore(ingestion_status)
    knowledge_summary = KnowledgeSourceSummaryStore(
        knowledge_sources, configured=bool(DATABASE_URL)
    )
    return OperationsSummaryService(
        health=lambda: _unknown_health(),
        maintenance=lambda: maintenance.get().enabled,
        cache=lambda: len(cache.list_regions()),
        jobs=jobs.counts,
        audit=lambda: audit.count_since(today),
        assistants=assistant_summary.counts,
        knowledge=knowledge_summary.counts,
        ingestion=ingestion_summary.counts,
    )


def _unknown_health() -> HealthOverview:
    return HealthOverview(status="unknown")
