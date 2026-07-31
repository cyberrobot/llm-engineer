from datetime import datetime, timedelta, timezone
from uuid import uuid4

from prometheus_client import CollectorRegistry

from assistant.application.ingestion_observability import IngestionProgressCalculator
from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_step_execution import IngestionStepExecutionStatus
from assistant.infrastructure.repositories.ingestion_observability import (
    InMemoryIngestionStepExecutionRepository,
)
from core.metrics import IngestionOperationalMetrics

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_progress_is_derived_from_durable_pipeline_state_and_retries_do_not_advance_it():
    job = DocumentIngestionJob.create(str(uuid4()), created_at=NOW)
    calculator = IngestionProgressCalculator(tuple(IngestionStep), now=lambda: NOW)

    queued = calculator.calculate(job)
    assert queued.completed_step_count == 0
    assert queued.total_step_count == 4
    assert queued.progress_percent == 0

    job.mark_running(at=NOW + timedelta(seconds=2))
    job.set_current_step(IngestionStep.chunk, at=NOW + timedelta(seconds=3))
    job.begin_step_attempt(at=NOW + timedelta(seconds=3))
    job.schedule_retry("timeout", "Provider timed out.", at=NOW + timedelta(seconds=4))
    running = calculator.calculate(job, at=NOW + timedelta(seconds=7))
    assert running.current_step is IngestionStep.chunk
    assert running.completed_step_count == 0
    assert running.progress_percent == 0
    assert running.current_step_attempt_count == 2
    assert running.queue_wait_duration_ms == 2_000
    assert running.processing_duration_ms == 5_000
    assert running.total_duration_ms == 7_000


def test_progress_counts_ordered_checkpoints_clamps_durations_and_completes_at_100_percent():
    job = DocumentIngestionJob.create(str(uuid4()), created_at=NOW)
    job.mark_running(at=NOW + timedelta(seconds=1))
    job.set_current_step(IngestionStep.parse, at=NOW + timedelta(seconds=1))
    job.begin_step_attempt(at=NOW + timedelta(seconds=1))
    job.mark_step_completed(IngestionStep.parse, at=NOW + timedelta(seconds=2))
    calculator = IngestionProgressCalculator(tuple(IngestionStep), now=lambda: NOW)

    partial = calculator.calculate(job, at=NOW - timedelta(seconds=5))
    assert partial.completed_step_count == 1
    assert partial.progress_percent == 25
    assert partial.processing_duration_ms == 0
    assert partial.total_duration_ms == 0

    for step in (IngestionStep.chunk, IngestionStep.embed, IngestionStep.persist):
        job.set_current_step(step, at=job.updated_at)
        job.begin_step_attempt(at=job.updated_at)
        job.mark_step_completed(step, at=job.updated_at)
    job.mark_completed(at=NOW + timedelta(seconds=10))
    completed = calculator.calculate(job)
    assert completed.completed_step_count == 4
    assert completed.progress_percent == 100
    assert completed.processing_duration_ms == 9_000
    assert completed.total_duration_ms == 10_000


def test_operational_metrics_use_only_bounded_labels():
    registry = CollectorRegistry()
    metrics = IngestionOperationalMetrics(registry=registry)

    metrics.job_created()
    metrics.step_attempt_started(IngestionStep.embed)
    metrics.step_attempt_completed(IngestionStep.embed, 1.25)
    metrics.step_retry(IngestionStep.embed, "provider_rate_limit")
    metrics.duplicate("completed_duplicate", pipeline_skipped=True)
    metrics.forced_reindex()
    metrics.persistence_rolled_back()
    metrics.job_completed(queue_wait_seconds=2.0, processing_seconds=5.0, total_seconds=7.0)

    samples = list(registry.collect())
    label_names = {
        label for family in samples for sample in family.samples for label in sample.labels
    }
    # ``le`` is prometheus-client's bounded histogram bucket label.
    assert label_names <= {"step", "failure_category", "retryable", "content_status", "le"}
    assert "job_id" not in label_names
    assert "document_id" not in label_names
    assert "worker_id" not in label_names


def test_progress_rejects_an_empty_pipeline_definition():
    try:
        IngestionProgressCalculator(())
    except ValueError as exc:
        assert "at least one step" in str(exc)
    else:
        raise AssertionError("An empty ingestion pipeline must not produce invented progress.")


def test_step_attempt_history_preserves_retries_and_marks_recovery_interruption():
    repository = InMemoryIngestionStepExecutionRepository()
    job_id = uuid4()

    first = repository.start_attempt(job_id, IngestionStep.embed, 1, started_at=NOW)
    repository.fail_attempt(
        job_id,
        IngestionStep.embed,
        1,
        completed_at=NOW + timedelta(seconds=2),
        duration_ms=2_000,
        failure_code="provider_timeout",
        retryable=True,
    )
    second = repository.start_attempt(
        job_id, IngestionStep.embed, 2, started_at=NOW + timedelta(seconds=3)
    )
    interrupted = repository.interrupt_running_attempts(job_id)
    third = repository.start_attempt(
        job_id, IngestionStep.embed, 3, started_at=NOW + timedelta(seconds=5)
    )
    repository.complete_attempt(
        job_id,
        IngestionStep.embed,
        3,
        completed_at=NOW + timedelta(seconds=6),
        duration_ms=1_000,
    )

    history = repository.list_for_job(job_id)
    assert first.attempt_number == 1
    assert second.attempt_number == 2
    assert third.attempt_number == 3
    assert interrupted == 1
    assert [attempt.status for attempt in history] == [
        IngestionStepExecutionStatus.failed,
        IngestionStepExecutionStatus.interrupted,
        IngestionStepExecutionStatus.completed,
    ]
    assert history[0].failure_code == "provider_timeout"
    assert history[0].retryable is True
    assert history[1].completed_at is None
    assert history[2].duration_ms == 1_000


def test_one_logical_step_attempt_has_at_most_one_terminal_result():
    repository = InMemoryIngestionStepExecutionRepository()
    job_id = uuid4()
    repository.start_attempt(job_id, IngestionStep.parse, 1, started_at=NOW)
    repository.complete_attempt(
        job_id,
        IngestionStep.parse,
        1,
        completed_at=NOW + timedelta(seconds=1),
        duration_ms=1_000,
    )

    try:
        repository.fail_attempt(
            job_id,
            IngestionStep.parse,
            1,
            completed_at=NOW + timedelta(seconds=2),
            duration_ms=2_000,
            failure_code="late_failure",
            retryable=False,
        )
    except ValueError as exc:
        assert "running" in str(exc)
    else:
        raise AssertionError("A completed attempt must not be overwritten.")
