from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID

from operations.domain.administration import (
    AuditEntry,
    AuditFilters,
    AuditPage,
    CacheRegionStatistics,
    JobCounts,
    JobPage,
    MaintenanceState,
    OperationalJob,
)


class InMemoryRuntimeStateStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._maintenance = MaintenanceState(
            False, None, datetime(1970, 1, 1, tzinfo=timezone.utc), None
        )

    def get_maintenance(self) -> MaintenanceState:
        with self._lock:
            return self._maintenance

    def set_maintenance(self, state: MaintenanceState) -> MaintenanceState:
        with self._lock:
            self._maintenance = state
            return state


class InMemoryCacheRegion:
    def __init__(self, name: str, entries: dict[str, object] | None = None) -> None:
        self.name = name
        self._entries = dict(entries or {})
        self._lock = RLock()

    def statistics(self) -> CacheRegionStatistics:
        with self._lock:
            return CacheRegionStatistics(name=self.name, entries=len(self._entries))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def clear_key(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._entries: dict[UUID, AuditEntry] = {}
        self._lock = RLock()

    def add(self, entry: AuditEntry) -> AuditEntry:
        with self._lock:
            self._entries[entry.id] = deepcopy(entry)
            return deepcopy(entry)

    def update(self, entry: AuditEntry) -> AuditEntry:
        with self._lock:
            if entry.id not in self._entries:
                raise LookupError("Audit entry does not exist.")
            self._entries[entry.id] = deepcopy(entry)
            return deepcopy(entry)

    def list(self, filters: AuditFilters, *, limit: int, offset: int) -> AuditPage:
        with self._lock:
            entries = [
                item
                for item in self._entries.values()
                if (filters.user is None or item.actor == filters.user)
                and (filters.action is None or item.action == filters.action)
                and (filters.resource is None or item.resource == filters.resource)
                and (filters.result is None or item.result is filters.result)
                and (filters.date_from is None or item.timestamp >= filters.date_from)
                and (filters.date_to is None or item.timestamp <= filters.date_to)
            ]
            entries.sort(key=lambda item: (item.timestamp, str(item.id)), reverse=True)
            return AuditPage(
                tuple(deepcopy(entries[offset : offset + limit])), len(entries), limit, offset
            )

    def get(self, entry_id: UUID) -> AuditEntry | None:
        with self._lock:
            entry = self._entries.get(entry_id)
            return deepcopy(entry) if entry else None

    def count_since(self, timestamp: datetime) -> int:
        with self._lock:
            return sum(item.timestamp >= timestamp for item in self._entries.values())


class InMemoryJobStore:
    def __init__(self, jobs: list[OperationalJob] | None = None) -> None:
        self._jobs = {job.id: job for job in jobs or []}

    def list(self, *, limit: int, offset: int, status: str | None = None) -> JobPage:
        jobs = [job for job in self._jobs.values() if status is None or job.status == status]
        jobs.sort(key=lambda job: (job.created_at, str(job.id)), reverse=True)
        return JobPage(tuple(jobs[offset : offset + limit]), len(jobs), limit, offset)

    def get(self, job_id: UUID) -> OperationalJob | None:
        return self._jobs.get(job_id)

    def counts(self) -> JobCounts:
        return JobCounts(
            running=sum(job.status == "running" for job in self._jobs.values()),
            failed=sum(job.status == "failed" for job in self._jobs.values()),
        )
