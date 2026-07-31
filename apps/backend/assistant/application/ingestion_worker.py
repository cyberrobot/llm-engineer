import logging
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from threading import Event, RLock, Thread
from time import monotonic
from uuid import UUID

from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from core.metrics import IngestionOperationalMetrics, ingestion_operational_metrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionJobClaim:
    job_id: UUID
    document_id: str
    worker_id: str
    claim_version: int
    claimed_at: datetime
    lease_expires_at: datetime
    recovered: bool


class WorkerExecutionResult(str, Enum):
    completed = "completed"
    failed = "failed"
    ownership_lost = "ownership_lost"
    interrupted = "interrupted"


class IngestionWorkerRepository:
    def claim_next(
        self, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim | None:
        raise NotImplementedError

    def renew_lease(
        self, claim: IngestionJobClaim, lease_duration: timedelta, now: datetime
    ) -> bool:
        raise NotImplementedError

    def claim_job(
        self, job_id: UUID, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim | None:
        raise NotImplementedError


@dataclass
class _OwnedJob:
    job: DocumentIngestionJob
    worker_id: str | None = None
    claim_version: int = 0
    claimed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class InMemoryIngestionWorkerRepository(IngestionWorkerRepository):
    """Thread-safe behavioral fake used by worker tests."""

    def __init__(self, jobs: Iterable[DocumentIngestionJob]) -> None:
        self._jobs = {job.id: _OwnedJob(deepcopy(job)) for job in jobs}
        self._lock = RLock()

    def get(self, job_id: UUID) -> DocumentIngestionJob:
        with self._lock:
            return deepcopy(self._jobs[job_id].job)

    def claim_next(
        self, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim | None:
        with self._lock:
            eligible = [
                owned
                for owned in self._jobs.values()
                if owned.job.status is IngestionStatus.queued
                or (
                    owned.job.status is IngestionStatus.running
                    and (owned.lease_expires_at is None or owned.lease_expires_at <= now)
                )
            ]
            eligible.sort(key=lambda owned: (owned.job.created_at, str(owned.job.id)))
            return self._claim(eligible[0], worker_id, lease_duration, now) if eligible else None

    def claim_job(
        self, job_id: UUID, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim | None:
        with self._lock:
            owned = self._jobs.get(job_id)
            if owned is None:
                return None
            if owned.job.status is IngestionStatus.queued or (
                owned.job.status is IngestionStatus.running
                and (owned.lease_expires_at is None or owned.lease_expires_at <= now)
            ):
                return self._claim(owned, worker_id, lease_duration, now)
            return None

    def _claim(
        self, owned: _OwnedJob, worker_id: str, lease_duration: timedelta, now: datetime
    ) -> IngestionJobClaim:
        recovered = owned.job.status is IngestionStatus.running
        if not recovered:
            owned.job.mark_running(at=now)
        elif owned.job.current_step is not None:
            owned.job.begin_step_attempt(at=now)
        owned.worker_id = worker_id
        owned.claim_version += 1
        owned.claimed_at = now
        owned.last_heartbeat_at = now
        owned.lease_expires_at = now + lease_duration
        return IngestionJobClaim(
            owned.job.id,
            owned.job.document_id,
            worker_id,
            owned.claim_version,
            now,
            owned.lease_expires_at,
            recovered,
        )

    def renew_lease(
        self, claim: IngestionJobClaim, lease_duration: timedelta, now: datetime
    ) -> bool:
        with self._lock:
            owned = self._jobs[claim.job_id]
            if (
                not self._owns(owned, claim)
                or owned.job.status is not IngestionStatus.running
                or owned.lease_expires_at is None
                or owned.lease_expires_at <= now
            ):
                return False
            owned.last_heartbeat_at = now
            owned.lease_expires_at = now + lease_duration
            return True

    def complete(self, claim: IngestionJobClaim, now: datetime) -> bool:
        with self._lock:
            owned = self._jobs[claim.job_id]
            if (
                not self._owns(owned, claim)
                or owned.job.status is not IngestionStatus.running
                or owned.lease_expires_at is None
                or owned.lease_expires_at <= now
            ):
                return False
            owned.job.mark_completed(at=now)
            owned.worker_id = None
            owned.lease_expires_at = None
            return True

    @staticmethod
    def _owns(owned: _OwnedJob, claim: IngestionJobClaim) -> bool:
        return owned.worker_id == claim.worker_id and owned.claim_version == claim.claim_version


class IngestionWorker:
    def __init__(
        self,
        repository: IngestionWorkerRepository,
        execute: Callable[[IngestionJobClaim], WorkerExecutionResult],
        *,
        worker_id: str,
        lease_duration: timedelta,
        poll_interval_seconds: float,
        wait: Callable[[float], bool],
        now: Callable[[], datetime],
        concurrency: int = 1,
        shutdown_grace_seconds: float = 30,
        metrics: IngestionOperationalMetrics = ingestion_operational_metrics,
    ) -> None:
        self._repository = repository
        self._execute = execute
        self._worker_id = worker_id
        self._lease_duration = lease_duration
        self._poll_interval_seconds = poll_interval_seconds
        self._wait = wait
        self._now = now
        self._concurrency = concurrency
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._metrics = metrics

    def run(self, stop: Event) -> None:
        logger.info("ingestion_worker_started", extra={"worker_id": self._worker_id})
        active: list[tuple[Thread, Event]] = []
        try:
            while not stop.is_set():
                active = [(thread, done) for thread, done in active if not done.is_set()]
                claimed_any = False
                while len(active) < self._concurrency and not stop.is_set():
                    try:
                        claim = self._repository.claim_next(
                            self._worker_id, self._lease_duration, self._now()
                        )
                    except Exception:
                        logger.exception("worker_poll_failed", extra={"worker_id": self._worker_id})
                        break
                    if claim is None:
                        break
                    claimed_any = True
                    logger.info(
                        "ingestion_job_recovered" if claim.recovered else "ingestion_job_claimed",
                        extra={
                            "worker_id": claim.worker_id,
                            "job_id": str(claim.job_id),
                            "document_id": claim.document_id,
                            "claim_version": claim.claim_version,
                            "lease_expires_at": claim.lease_expires_at,
                        },
                    )
                    self._metric("job_recovered" if claim.recovered else "job_claimed")
                    done = Event()
                    thread = Thread(
                        target=self._execute_and_signal,
                        args=(claim, done),
                        name=f"ingestion-job-{claim.job_id}",
                        daemon=True,
                    )
                    active.append((thread, done))
                    thread.start()
                if len(active) >= self._concurrency:
                    stop.wait(min(self._poll_interval_seconds, 0.5))
                elif not claimed_any:
                    self._wait(self._poll_interval_seconds)
        finally:
            deadline = monotonic() + self._shutdown_grace_seconds
            for thread, _done in active:
                thread.join(max(0, deadline - monotonic()))
            unfinished = [(thread, done) for thread, done in active if not done.is_set()]
            if unfinished:
                logger.warning(
                    "ingestion_job_execution_interrupted",
                    extra={"worker_id": self._worker_id, "reason": "shutdown_grace_expired"},
                )
                shutdown = getattr(self._execute, "shutdown", None)
                if shutdown is not None:
                    shutdown()
            logger.info("ingestion_worker_stopped", extra={"worker_id": self._worker_id})

    def _execute_and_signal(self, claim: IngestionJobClaim, done: Event) -> None:
        started = monotonic()
        try:
            result = self._execute(claim)
            if result is WorkerExecutionResult.ownership_lost:
                self._metric("lease_lost")
        except Exception:
            logger.exception(
                "ingestion_job_execution_interrupted",
                extra={
                    "worker_id": claim.worker_id,
                    "job_id": str(claim.job_id),
                    "claim_version": claim.claim_version,
                },
            )
        finally:
            self._metric("worker_executed", max(0, monotonic() - started))
            done.set()

    def _metric(self, method: str, *args: object) -> None:
        try:
            getattr(self._metrics, method)(*args)
        except Exception:
            logger.warning("ingestion_telemetry_export_failed", extra={"reason": method})
