from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from time import monotonic

from assistant.application.ingestion_worker import (
    IngestionWorker,
    InMemoryIngestionWorkerRepository,
    WorkerExecutionResult,
)
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus

NOW = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)


def queued(document_id: str, *, created_at: datetime) -> DocumentIngestionJob:
    return DocumentIngestionJob.create(document_id, created_at=created_at)


def test_claims_oldest_queued_job_and_persists_fenced_ownership():
    newer = queued("document-2", created_at=NOW + timedelta(seconds=1))
    older = queued("document-1", created_at=NOW)
    repository = InMemoryIngestionWorkerRepository([newer, older])

    claim = repository.claim_next("worker-a", timedelta(seconds=60), NOW)

    assert claim is not None
    assert claim.job_id == older.id
    assert claim.worker_id == "worker-a"
    assert claim.claim_version == 1
    assert claim.lease_expires_at == NOW + timedelta(seconds=60)
    assert repository.get(older.id).status is IngestionStatus.running


def test_claim_skips_terminal_and_live_jobs_and_recovers_expired_state_without_resetting_it():
    completed = queued("completed", created_at=NOW - timedelta(minutes=3))
    completed.mark_running(at=NOW - timedelta(minutes=3))
    completed.mark_completed(at=NOW - timedelta(minutes=2))
    active = queued("active", created_at=NOW - timedelta(minutes=2))
    expired = queued("expired", created_at=NOW - timedelta(minutes=1))
    expired.mark_running(at=NOW - timedelta(minutes=1))
    expired.set_current_step(IngestionStep.embed, at=NOW - timedelta(seconds=50))
    expired.begin_step_attempt(at=NOW - timedelta(seconds=49))
    expired.schedule_retry("timeout", "Timed out.", at=NOW - timedelta(seconds=48))
    repository = InMemoryIngestionWorkerRepository([completed, active, expired])
    active_claim = repository.claim_job(active.id, "worker-a", timedelta(seconds=60), NOW)
    old_claim = repository.claim_job(
        expired.id, "worker-old", timedelta(seconds=1), NOW - timedelta(seconds=2)
    )
    assert active_claim and old_claim

    recovered = repository.claim_next("worker-b", timedelta(seconds=60), NOW)

    assert recovered is not None
    assert recovered.job_id == expired.id
    assert recovered.recovered is True
    assert recovered.claim_version == old_claim.claim_version + 1
    stored = repository.get(expired.id)
    assert stored.last_completed_step is expired.last_completed_step
    assert stored.current_step is IngestionStep.embed
    assert stored.retry_count == 1
    assert repository.claim_next("worker-c", timedelta(seconds=60), NOW) is None


def test_heartbeat_and_terminal_updates_reject_stale_owner_and_claim_version():
    job = queued("document-1", created_at=NOW)
    repository = InMemoryIngestionWorkerRepository([job])
    first = repository.claim_next("worker-a", timedelta(seconds=5), NOW)
    assert first
    second = repository.claim_next("worker-b", timedelta(seconds=60), NOW + timedelta(seconds=6))
    assert second

    assert not repository.renew_lease(first, timedelta(seconds=60), NOW + timedelta(seconds=7))
    assert not repository.complete(first, NOW + timedelta(seconds=8))
    assert repository.renew_lease(second, timedelta(seconds=60), NOW + timedelta(seconds=7))
    assert repository.complete(second, NOW + timedelta(seconds=8))
    assert repository.get(job.id).status is IngestionStatus.completed


def test_expired_owner_cannot_complete_even_before_another_worker_reclaims():
    job = queued("document-1", created_at=NOW)
    repository = InMemoryIngestionWorkerRepository([job])
    claim = repository.claim_next("worker-a", timedelta(seconds=5), NOW)
    assert claim

    assert not repository.renew_lease(claim, timedelta(seconds=60), NOW + timedelta(seconds=6))
    assert not repository.complete(claim, NOW + timedelta(seconds=6))
    assert repository.get(job.id).status is IngestionStatus.running


def test_worker_executes_claimed_job_and_continues_after_execution_exception():
    first = queued("document-1", created_at=NOW)
    second = queued("document-2", created_at=NOW + timedelta(seconds=1))
    repository = InMemoryIngestionWorkerRepository([first, second])
    calls = []

    def execute(claim):
        calls.append(claim.job_id)
        if claim.job_id == first.id:
            raise RuntimeError("simulated crash")
        repository.complete(claim, NOW + timedelta(seconds=2))
        return WorkerExecutionResult.completed

    waits = []
    stop = Event()

    def wait(seconds):
        waits.append(seconds)
        if len(calls) == 2:
            stop.set()
        return stop.is_set()

    worker = IngestionWorker(
        repository,
        execute,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=60),
        poll_interval_seconds=0.1,
        wait=wait,
        now=lambda: NOW + timedelta(seconds=1),
    )
    worker.run(stop)

    assert calls == [first.id, second.id]
    assert waits
    assert repository.get(first.id).status is IngestionStatus.running
    assert repository.get(second.id).status is IngestionStatus.completed


def test_worker_waits_when_empty_and_stops_without_claiming_after_shutdown():
    repository = InMemoryIngestionWorkerRepository([])
    stop = Event()
    waits = []

    def wait(seconds):
        waits.append(seconds)
        stop.set()
        return True

    worker = IngestionWorker(
        repository,
        lambda claim: WorkerExecutionResult.completed,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=60),
        poll_interval_seconds=0.25,
        wait=wait,
        now=lambda: NOW,
    )
    worker.run(stop)

    assert waits == [0.25]


def test_worker_honours_bounded_concurrency():
    jobs = [queued(f"document-{index}", created_at=NOW) for index in range(2)]
    repository = InMemoryIngestionWorkerRepository(jobs)
    barrier = Barrier(2)
    stop = Event()
    lock = Lock()
    active = 0
    maximum_active = 0

    def execute(claim):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        barrier.wait(timeout=2)
        repository.complete(claim, NOW + timedelta(seconds=1))
        with lock:
            active -= 1
            if active == 0:
                stop.set()
        return WorkerExecutionResult.completed

    worker = IngestionWorker(
        repository,
        execute,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=60),
        poll_interval_seconds=0.01,
        wait=stop.wait,
        now=lambda: NOW,
        concurrency=2,
    )
    worker.run(stop)

    assert maximum_active == 2
    assert all(repository.get(job.id).status is IngestionStatus.completed for job in jobs)


def test_worker_stops_heartbeats_and_returns_after_shutdown_grace():
    job = queued("document-1", created_at=NOW)
    repository = InMemoryIngestionWorkerRepository([job])
    stop = Event()
    release = Event()

    class BlockingExecutor:
        def __init__(self):
            self.shutdown_called = False

        def __call__(self, claim):
            stop.set()
            release.wait(2)
            return WorkerExecutionResult.interrupted

        def shutdown(self):
            self.shutdown_called = True

    executor = BlockingExecutor()
    worker = IngestionWorker(
        repository,
        executor,
        worker_id="worker-a",
        lease_duration=timedelta(seconds=60),
        poll_interval_seconds=1,
        wait=stop.wait,
        now=lambda: NOW,
        shutdown_grace_seconds=0.01,
    )

    started = monotonic()
    worker.run(stop)
    elapsed = monotonic() - started
    release.set()

    assert elapsed < 0.5
    assert executor.shutdown_called
    assert repository.get(job.id).status is IngestionStatus.running
