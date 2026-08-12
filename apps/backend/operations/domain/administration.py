from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class CacheRegionNotFound(LookupError):
    pass


class CacheKeyNotFound(LookupError):
    pass


class AuditEntryNotFound(LookupError):
    pass


class OperationalJobNotFound(LookupError):
    pass


class OperationsDependencyUnavailable(RuntimeError):
    pass


class AuditResult(str, Enum):
    started = "STARTED"
    success = "SUCCESS"
    failure = "FAILURE"


@dataclass(frozen=True)
class CacheRegionStatistics:
    name: str
    entries: int | None = None
    estimated_memory_bytes: int | None = None
    hit_count: int | None = None
    miss_count: int | None = None
    hit_ratio: float | None = None


@dataclass(frozen=True)
class MaintenanceState:
    enabled: bool
    message: str | None
    updated_at: datetime
    updated_by: str | None


@dataclass(frozen=True)
class AuditEntry:
    id: UUID
    timestamp: datetime
    actor: str
    action: str
    resource: str
    result: AuditResult
    request_id: str
    correlation_id: str
    duration_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditFilters:
    user: str | None = None
    action: str | None = None
    resource: str | None = None
    result: AuditResult | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True)
class AuditPage:
    items: tuple[AuditEntry, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class OperationalJob:
    id: UUID
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    retry_count: int
    last_error: str | None
    execution_node: str | None = None
    job_type: str = "ingestion"

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return max(0, round((self.completed_at - self.started_at).total_seconds() * 1000))


@dataclass(frozen=True)
class JobPage:
    items: tuple[OperationalJob, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class JobCounts:
    running: int
    failed: int


@dataclass(frozen=True)
class AssistantCounts:
    total: int
    published: int


@dataclass(frozen=True)
class KnowledgeSourceCounts:
    total: int
    enabled: int
    failed: int | None


@dataclass(frozen=True)
class IngestionCounts:
    queued: int
    running: int
    recoverable: int
    failed: int
    oldest_queued_age_seconds: float
    workers_observed: int


@dataclass(frozen=True)
class HealthOverview:
    status: str


@dataclass(frozen=True)
class OperationalSummary:
    generated_at: datetime
    health: str
    maintenance: bool
    cache_regions: int
    running_jobs: int
    failed_jobs: int
    audit_today: int
    assistants: AssistantCounts
    knowledge_sources: KnowledgeSourceCounts
    ingestion: IngestionCounts
