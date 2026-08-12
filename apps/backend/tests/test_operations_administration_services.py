from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from assistant.application.ingestion_observability import IngestionOperationalStatus
from assistant.application.ports.knowledge_source_repository import KnowledgeSourceAggregate
from assistant.domain.assistant_repository import AssistantAggregate
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)
from operations.application.administration import (
    AuditQueryService,
    CacheAdministrationService,
    MaintenanceService,
    OperationsSummaryService,
)
from operations.domain.administration import (
    AssistantCounts,
    AuditEntry,
    AuditFilters,
    AuditResult,
    CacheKeyNotFound,
    CacheRegionNotFound,
    HealthOverview,
    IngestionCounts,
    JobCounts,
    KnowledgeSourceCounts,
    OperationsDependencyUnavailable,
)
from operations.infrastructure.dashboard import (
    AssistantSummaryStore,
    IngestionSummaryStore,
    KnowledgeSourceSummaryStore,
)
from operations.infrastructure.jobs import IngestionJobOperationsStore
from operations.infrastructure.memory import (
    InMemoryAuditStore,
    InMemoryCacheRegion,
    InMemoryRuntimeStateStore,
)

NOW = datetime(2026, 8, 11, 10, tzinfo=timezone.utc)


def test_maintenance_service_is_idempotent_and_validates_messages():
    service = MaintenanceService(InMemoryRuntimeStateStore(), now=lambda: NOW)

    initial = service.get()
    enabled = service.update(enabled=True, message=None, actor="operator")
    repeated = service.update(enabled=True, message=None, actor="operator")
    disabled = service.update(enabled=False, message="ignored", actor="operator")
    repeated_disabled = service.update(enabled=False, message=None, actor="operator")

    assert initial.enabled is False
    assert enabled == repeated
    assert enabled.enabled is True
    assert enabled.message is None
    assert enabled.updated_by == "operator"
    assert disabled == repeated_disabled
    assert disabled.enabled is False
    assert disabled.message is None
    with pytest.raises(ValueError, match="message"):
        service.update(enabled=True, message="x" * 501, actor="operator")


def test_cache_administration_reports_unavailable_metrics_as_none_and_clears_idempotently():
    region = InMemoryCacheRegion("assistant", entries={"assistant:123": "value"})
    service = CacheAdministrationService({"assistant": region})

    stats = service.list_regions()

    assert stats[0].name == "assistant"
    assert stats[0].entries == 1
    assert stats[0].estimated_memory_bytes is None
    assert stats[0].hit_count is None
    assert stats[0].miss_count is None
    assert stats[0].hit_ratio is None
    service.invalidate_key("assistant", "assistant:123")
    with pytest.raises(CacheKeyNotFound):
        service.invalidate_key("assistant", "assistant:123")
    service.clear_region("assistant")
    service.clear_all()
    assert service.list_regions()[0].entries == 0
    with pytest.raises(CacheRegionNotFound):
        service.clear_region("unknown")


def test_audit_queries_are_newest_first_filtered_paginated_and_redacted():
    store = InMemoryAuditStore()
    service = AuditQueryService(store)
    service.record(
        actor="first@example.test",
        action="cache.clear",
        resource="cache:assistant",
        result=AuditResult.success,
        request_id="request-1",
        correlation_id="correlation-1",
        duration_ms=12,
        metadata={
            "session_token": "secret",
            "authorization_header": "Bearer secret",
            "private_config": {"password": "secret"},
            "safe": "shown",
        },
        timestamp=NOW - timedelta(minutes=1),
    )
    latest = service.record(
        actor="second@example.test",
        action="maintenance.update",
        resource="maintenance",
        result=AuditResult.success,
        request_id="request-2",
        correlation_id="correlation-2",
        duration_ms=3,
        metadata={"enabled": True},
        timestamp=NOW,
    )

    page = service.list(AuditFilters(action="maintenance.update"), limit=1, offset=0)

    assert page.total == 1
    assert page.items == (latest,)
    first = service.list(AuditFilters(), limit=10, offset=0).items[1]
    assert first.metadata == {
        "authorization_header": "[REDACTED]",
        "private_config": "[REDACTED]",
        "safe": "shown",
        "session_token": "[REDACTED]",
    }


def test_audit_intent_is_durable_before_completion():
    store = InMemoryAuditStore()
    service = AuditQueryService(store, now=lambda: NOW)

    started = service.start(
        actor="operator",
        action="cache.clear",
        resource="cache",
        request_id="request",
        correlation_id="correlation",
    )

    assert store.get(started.id).result is AuditResult.started
    completed = service.finish(started, result=AuditResult.success, duration_ms=5)
    assert store.get(started.id) == completed


def test_audit_browsing_redacts_unsafe_metadata_already_present_in_the_store():
    store = InMemoryAuditStore()
    entry = AuditEntry(
        id=uuid4(),
        timestamp=NOW,
        actor="operator",
        action="legacy.action",
        resource="legacy",
        result=AuditResult.success,
        request_id="request",
        correlation_id="correlation",
        duration_ms=1,
        metadata={"session_token": "legacy-secret", "status": "safe"},
    )
    store.add(entry)

    returned = AuditQueryService(store).get(entry.id)

    assert returned.metadata == {"session_token": "[REDACTED]", "status": "safe"}


def test_job_visibility_reuses_ingestion_repository_with_safe_projection_and_pagination():
    repository = InMemoryDocumentIngestionJobRepository(document_ids={"doc-1", "doc-2"})
    failed = DocumentIngestionJob.create(
        "doc-1",
        job_id=UUID("00000000-0000-0000-0000-000000000001"),
        created_at=NOW - timedelta(minutes=2),
    )
    failed.mark_running(at=NOW - timedelta(seconds=90))
    failed.mark_failed(
        "provider_unavailable",
        "Bearer private-token must never be returned",
        at=NOW - timedelta(minutes=1),
    )
    queued = DocumentIngestionJob.create(
        "doc-2",
        job_id=UUID("00000000-0000-0000-0000-000000000002"),
        created_at=NOW,
    )
    repository.create(failed)
    repository.create(queued)
    store = IngestionJobOperationsStore(repository)

    first_page = store.list(limit=1, offset=0)
    second_page = store.list(limit=1, offset=1)
    failures = store.list(limit=10, offset=0, status="failed")

    assert first_page.total == 2
    assert first_page.items[0].id == queued.id
    assert second_page.items[0].id == failed.id
    assert failures.items[0].last_error == "provider_unavailable"
    assert "private-token" not in repr(failures.items[0])
    assert store.get(failed.id) == failures.items[0]
    assert store.counts() == JobCounts(running=0, failed=1)
    assert failures.items[0].job_type == "ingestion"


def test_summary_aggregates_each_service_once():
    calls = {
        "health": 0,
        "maintenance": 0,
        "cache": 0,
        "jobs": 0,
        "audit": 0,
        "assistants": 0,
        "knowledge": 0,
        "ingestion": 0,
        "now": 0,
    }

    def value(name, result):
        calls[name] += 1
        return result

    service = OperationsSummaryService(
        health=lambda: value("health", HealthOverview(status="healthy")),
        maintenance=lambda: value("maintenance", False),
        cache=lambda: value("cache", 2),
        jobs=lambda: value("jobs", JobCounts(running=1, failed=3)),
        audit=lambda: value("audit", 7),
        assistants=lambda: value("assistants", AssistantCounts(total=4, published=3)),
        knowledge=lambda: value(
            "knowledge", KnowledgeSourceCounts(total=9, enabled=8, failed=None)
        ),
        ingestion=lambda now: value(
            "ingestion",
            IngestionCounts(
                queued=5,
                running=2,
                recoverable=1,
                failed=6,
                oldest_queued_age_seconds=84.5,
                workers_observed=2,
            ),
        ),
        now=lambda: value("now", NOW),
    )

    summary = service.get()

    assert summary.health == "healthy"
    assert summary.maintenance is False
    assert summary.cache_regions == 2
    assert summary.running_jobs == 1
    assert summary.failed_jobs == 3
    assert summary.audit_today == 7
    assert summary.generated_at == NOW
    assert summary.assistants == AssistantCounts(total=4, published=3)
    assert summary.knowledge_sources == KnowledgeSourceCounts(total=9, enabled=8, failed=None)
    assert summary.ingestion.failed == 6
    assert calls == {
        "health": 1,
        "maintenance": 1,
        "cache": 1,
        "jobs": 1,
        "audit": 1,
        "assistants": 1,
        "knowledge": 1,
        "ingestion": 1,
        "now": 1,
    }


def test_summary_preserves_authoritative_zero_state_without_inventing_source_failures():
    service = OperationsSummaryService(
        health=lambda: HealthOverview(status="healthy"),
        maintenance=lambda: False,
        cache=lambda: 0,
        jobs=lambda: JobCounts(running=0, failed=0),
        audit=lambda: 0,
        assistants=lambda: AssistantCounts(total=0, published=0),
        knowledge=lambda: KnowledgeSourceCounts(total=0, enabled=0, failed=None),
        ingestion=lambda _now: IngestionCounts(0, 0, 0, 0, 0.0, 0),
        now=lambda: NOW,
    )

    summary = service.get()

    assert summary.assistants.total == 0
    assert summary.knowledge_sources.failed is None
    assert summary.ingestion == IngestionCounts(0, 0, 0, 0, 0.0, 0)


def test_summary_propagates_dependency_failure_for_the_standard_operations_error_contract():
    def unavailable():
        raise OperationsDependencyUnavailable("internal dependency detail")

    service = OperationsSummaryService(
        health=unavailable,
        maintenance=lambda: False,
        cache=lambda: 0,
        jobs=lambda: JobCounts(running=0, failed=0),
        audit=lambda: 0,
        assistants=lambda: AssistantCounts(total=0, published=0),
        knowledge=lambda: KnowledgeSourceCounts(total=0, enabled=0, failed=None),
        ingestion=lambda _now: IngestionCounts(0, 0, 0, 0, 0.0, 0),
        now=lambda: NOW,
    )

    with pytest.raises(OperationsDependencyUnavailable):
        service.get()


def test_dashboard_stores_use_authoritative_aggregate_queries_and_preserve_queue_age():
    class Assistants:
        def aggregate_counts(self):
            return AssistantAggregate(total=5, published=4)

    class Knowledge:
        def aggregate_counts(self):
            return KnowledgeSourceAggregate(total=12, enabled=9)

    class Ingestion:
        def get(self, *, now):
            assert now == NOW
            return IngestionOperationalStatus(
                queued_jobs=7,
                running_jobs=3,
                recoverable_jobs=2,
                oldest_queued_age_seconds=125.25,
                workers_observed=2,
                failed_jobs=6,
            )

    assert AssistantSummaryStore(Assistants()).counts() == AssistantCounts(5, 4)
    assert KnowledgeSourceSummaryStore(Knowledge()).counts() == KnowledgeSourceCounts(12, 9, None)
    assert IngestionSummaryStore(Ingestion()).counts(NOW) == IngestionCounts(7, 3, 2, 6, 125.25, 2)


@pytest.mark.parametrize(
    "store",
    [
        AssistantSummaryStore(
            type("Assistants", (), {"aggregate_counts": lambda self: _database_failure()})(),
        ),
        KnowledgeSourceSummaryStore(
            type("Knowledge", (), {"aggregate_counts": lambda self: _database_failure()})()
        ),
        IngestionSummaryStore(
            type("Ingestion", (), {"get": lambda self, *, now: _database_failure()})()
        ),
    ],
)
def test_dashboard_stores_map_database_failures_to_operations_dependency_unavailable(store):
    with pytest.raises(OperationsDependencyUnavailable):
        store.counts(NOW) if isinstance(store, IngestionSummaryStore) else store.counts()


def test_knowledge_summary_reports_an_unconfigured_dependency_instead_of_zero():
    repository = type(
        "Knowledge", (), {"aggregate_counts": lambda self: KnowledgeSourceAggregate(0, 0)}
    )()

    with pytest.raises(OperationsDependencyUnavailable):
        KnowledgeSourceSummaryStore(repository, configured=False).counts()


def _database_failure():
    raise psycopg.OperationalError("private database address")
