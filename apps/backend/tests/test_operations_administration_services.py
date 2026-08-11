from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

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
    AuditEntry,
    AuditFilters,
    AuditResult,
    CacheKeyNotFound,
    CacheRegionNotFound,
    HealthOverview,
    JobCounts,
    OperationsDependencyUnavailable,
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


def test_summary_aggregates_each_service_once():
    calls = {"health": 0, "maintenance": 0, "cache": 0, "jobs": 0, "audit": 0}

    def value(name, result):
        calls[name] += 1
        return result

    service = OperationsSummaryService(
        health=lambda: value("health", HealthOverview(status="healthy")),
        maintenance=lambda: value("maintenance", False),
        cache=lambda: value("cache", 2),
        jobs=lambda: value("jobs", JobCounts(running=1, failed=3)),
        audit=lambda: value("audit", 7),
    )

    summary = service.get()

    assert summary.health == "healthy"
    assert summary.maintenance is False
    assert summary.cache_regions == 2
    assert summary.running_jobs == 1
    assert summary.failed_jobs == 3
    assert summary.audit_today == 7
    assert calls == {"health": 1, "maintenance": 1, "cache": 1, "jobs": 1, "audit": 1}


def test_summary_propagates_dependency_failure_for_the_standard_operations_error_contract():
    def unavailable():
        raise OperationsDependencyUnavailable("internal dependency detail")

    service = OperationsSummaryService(
        health=unavailable,
        maintenance=lambda: False,
        cache=lambda: 0,
        jobs=lambda: JobCounts(running=0, failed=0),
        audit=lambda: 0,
    )

    with pytest.raises(OperationsDependencyUnavailable):
        service.get()
