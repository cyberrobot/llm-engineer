from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID, uuid4

from operations.domain.administration import (
    AssistantCounts,
    AuditEntry,
    AuditEntryNotFound,
    AuditFilters,
    AuditPage,
    AuditResult,
    CacheKeyNotFound,
    CacheRegionNotFound,
    CacheRegionStatistics,
    HealthOverview,
    IngestionCounts,
    JobCounts,
    JobPage,
    KnowledgeSourceCounts,
    MaintenanceState,
    OperationalJob,
    OperationalJobNotFound,
    OperationalSummary,
)


class CacheRegion(Protocol):
    name: str

    def statistics(self) -> CacheRegionStatistics: ...

    def clear(self) -> None: ...

    def clear_key(self, key: str) -> bool: ...


class RuntimeStateStore(Protocol):
    def get_maintenance(self) -> MaintenanceState: ...

    def set_maintenance(self, state: MaintenanceState) -> MaintenanceState: ...


class AuditStore(Protocol):
    def add(self, entry: AuditEntry) -> AuditEntry: ...

    def update(self, entry: AuditEntry) -> AuditEntry: ...

    def list(self, filters: AuditFilters, *, limit: int, offset: int) -> AuditPage: ...

    def get(self, entry_id: UUID) -> AuditEntry | None: ...

    def count_since(self, timestamp: datetime) -> int: ...


class JobStore(Protocol):
    def list(self, *, limit: int, offset: int, status: str | None = None) -> JobPage: ...

    def get(self, job_id: UUID) -> OperationalJob | None: ...

    def counts(self) -> JobCounts: ...


class CacheAdministrationService:
    def __init__(self, regions: Mapping[str, CacheRegion]) -> None:
        self._regions = dict(regions)

    def list_regions(self) -> tuple[CacheRegionStatistics, ...]:
        return tuple(self._regions[name].statistics() for name in sorted(self._regions))

    def clear_all(self) -> None:
        for name in sorted(self._regions):
            self._regions[name].clear()

    def clear_region(self, name: str) -> None:
        self._region(name).clear()

    def invalidate_key(self, region: str, key: str) -> None:
        if not self._region(region).clear_key(key):
            raise CacheKeyNotFound(key)

    def _region(self, name: str) -> CacheRegion:
        try:
            return self._regions[name]
        except KeyError as exc:
            raise CacheRegionNotFound(name) from exc


class MaintenanceService:
    def __init__(
        self, store: RuntimeStateStore, *, now: Callable[[], datetime] | None = None
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get(self) -> MaintenanceState:
        return self._store.get_maintenance()

    def update(self, *, enabled: bool, message: str | None, actor: str) -> MaintenanceState:
        normalized = message.strip() if message else None
        if normalized and len(normalized) > 500:
            raise ValueError("The maintenance message is too long.")
        current = self.get()
        desired_message = normalized if enabled else None
        if current.enabled == enabled and current.message == desired_message:
            return current
        return self._store.set_maintenance(
            MaintenanceState(enabled, desired_message, self._now(), actor)
        )


class AuditQueryService:
    _SAFE_METADATA_KEYS = {"enabled", "failure_type", "no_op", "region", "safe", "status"}

    def __init__(self, store: AuditStore, *, now: Callable[[], datetime] | None = None) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def record(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        result: AuditResult,
        request_id: str,
        correlation_id: str,
        duration_ms: int,
        metadata: Mapping[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=uuid4(),
            timestamp=timestamp or self._now(),
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            request_id=request_id,
            correlation_id=correlation_id,
            duration_ms=max(0, duration_ms),
            metadata=self._redact(dict(metadata or {})),
        )
        return self._store.add(entry)

    def start(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        request_id: str,
        correlation_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        return self.record(
            actor=actor,
            action=action,
            resource=resource,
            result=AuditResult.started,
            request_id=request_id,
            correlation_id=correlation_id,
            duration_ms=0,
            metadata=metadata,
        )

    def finish(
        self,
        entry: AuditEntry,
        *,
        result: AuditResult,
        duration_ms: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        if result is AuditResult.started:
            raise ValueError("A completed audit entry requires a terminal result.")
        merged_metadata = {**entry.metadata, **dict(metadata or {})}
        completed = replace(
            entry,
            result=result,
            duration_ms=max(0, duration_ms),
            metadata=self._redact(merged_metadata),
        )
        return self._store.update(completed)

    def list(self, filters: AuditFilters, *, limit: int, offset: int) -> AuditPage:
        page = self._store.list(filters, limit=limit, offset=offset)
        return replace(
            page,
            items=tuple(self._sanitize_entry(entry) for entry in page.items),
        )

    def get(self, entry_id: UUID) -> AuditEntry:
        entry = self._store.get(entry_id)
        if entry is None:
            raise AuditEntryNotFound(str(entry_id))
        return self._sanitize_entry(entry)

    def count_since(self, timestamp: datetime) -> int:
        return self._store.count_since(timestamp)

    @classmethod
    def _redact(cls, value: Any, key: str | None = None) -> Any:
        if key is not None and key.casefold() not in cls._SAFE_METADATA_KEYS:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {item_key: cls._redact(item, item_key) for item_key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value

    @classmethod
    def _sanitize_entry(cls, entry: AuditEntry) -> AuditEntry:
        return replace(entry, metadata=cls._redact(entry.metadata))


class JobOperationsService:
    def __init__(self, store: JobStore) -> None:
        self._store = store

    def list(self, *, limit: int, offset: int, status: str | None = None) -> JobPage:
        return self._store.list(limit=limit, offset=offset, status=status)

    def get(self, job_id: UUID) -> OperationalJob:
        job = self._store.get(job_id)
        if job is None:
            raise OperationalJobNotFound(str(job_id))
        return job

    def counts(self) -> JobCounts:
        return self._store.counts()


class OperationsSummaryService:
    def __init__(
        self,
        *,
        health: Callable[[], HealthOverview],
        maintenance: Callable[[], bool],
        cache: Callable[[], int],
        jobs: Callable[[], JobCounts],
        audit: Callable[[], int],
        assistants: Callable[[], AssistantCounts],
        knowledge: Callable[[], KnowledgeSourceCounts],
        ingestion: Callable[[datetime], IngestionCounts],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._health = health
        self._maintenance = maintenance
        self._cache = cache
        self._jobs = jobs
        self._audit = audit
        self._assistants = assistants
        self._knowledge = knowledge
        self._ingestion = ingestion
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get(self, *, health_override: HealthOverview | None = None) -> OperationalSummary:
        generated_at = self._now()
        health = health_override or self._health()
        maintenance = self._maintenance()
        cache_regions = self._cache()
        jobs = self._jobs()
        audit_today = self._audit()
        assistants = self._assistants()
        knowledge_sources = self._knowledge()
        ingestion = self._ingestion(generated_at)
        return OperationalSummary(
            generated_at=generated_at,
            health=health.status,
            maintenance=maintenance,
            cache_regions=cache_regions,
            running_jobs=jobs.running,
            failed_jobs=jobs.failed,
            audit_today=audit_today,
            assistants=assistants,
            knowledge_sources=knowledge_sources,
            ingestion=ingestion,
        )


def elapsed_milliseconds(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
