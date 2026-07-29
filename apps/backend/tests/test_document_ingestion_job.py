from datetime import datetime, timedelta, timezone

import pytest

from assistant.domain.document_ingestion_job import (
    DocumentIngestionJob,
    IngestionStep,
    InvalidDocumentIngestionJob,
)
from assistant.domain.ingestion_status import IngestionStatus

NOW = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)


def test_new_document_ingestion_job_starts_queued_with_future_state_unset():
    job = DocumentIngestionJob.create("3f45bc1b-d132-4ed2-b91f-598708d572a1", created_at=NOW)

    assert job.status is IngestionStatus.queued
    assert job.retry_count == 0
    assert job.current_step is None
    assert job.last_completed_step is None
    assert job.failure_code is None
    assert job.failure_message is None
    assert job.started_at is None
    assert job.completed_at is None
    assert job.created_at == job.updated_at == NOW


def test_job_supports_queued_running_completed_lifecycle_and_step_changes():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    started = NOW + timedelta(seconds=1)
    stepped = started + timedelta(seconds=1)
    completed = stepped + timedelta(seconds=1)

    job.mark_running(at=started)
    job.set_current_step(IngestionStep.parse, at=stepped)
    job.mark_step_completed(IngestionStep.parse, at=stepped)
    job.mark_completed(at=completed)

    assert job.status is IngestionStatus.completed
    assert job.started_at == started
    assert job.current_step is None
    assert job.last_completed_step is IngestionStep.parse
    assert job.completed_at == job.updated_at == completed
    assert job.failure_code is None
    assert job.failure_message is None


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_terminal_jobs_reject_transitions_steps_and_retry_increment(terminal):
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    job.mark_running(at=NOW + timedelta(seconds=1))
    if terminal == "completed":
        job.mark_completed(at=NOW + timedelta(seconds=2))
    elif terminal == "failed":
        job.mark_failed("parse_failed", "Could not parse document", at=NOW + timedelta(seconds=2))
    else:
        job.mark_cancelled(at=NOW + timedelta(seconds=2))

    with pytest.raises(InvalidDocumentIngestionJob, match="terminal"):
        job.mark_cancelled(at=NOW + timedelta(seconds=3))
    with pytest.raises(InvalidDocumentIngestionJob, match="terminal"):
        job.set_current_step(IngestionStep.chunk, at=NOW + timedelta(seconds=3))
    with pytest.raises(InvalidDocumentIngestionJob, match="terminal"):
        job.increment_retry_count(at=NOW + timedelta(seconds=3))


def test_queued_job_can_be_cancelled_but_cannot_complete_or_fail():
    for operation in (
        lambda job: job.mark_completed(at=NOW + timedelta(seconds=1)),
        lambda job: job.mark_failed("failed", None, at=NOW + timedelta(seconds=1)),
    ):
        with pytest.raises(InvalidDocumentIngestionJob, match="transition"):
            operation(DocumentIngestionJob.create("document-1", created_at=NOW))

    cancelled = DocumentIngestionJob.create("document-1", created_at=NOW)
    cancelled.mark_cancelled(at=NOW + timedelta(seconds=1))
    assert cancelled.status is IngestionStatus.cancelled
    assert cancelled.completed_at == NOW + timedelta(seconds=1)


def test_running_job_rejects_a_second_start_without_overwriting_started_at():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    started = NOW + timedelta(seconds=1)
    job.mark_running(at=started)

    with pytest.raises(InvalidDocumentIngestionJob, match="transition"):
        job.mark_running(at=NOW + timedelta(seconds=2))

    assert job.started_at == started


def test_non_terminal_job_can_increment_retry_count_and_updates_timestamp():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    retried_at = NOW + timedelta(seconds=1)

    job.increment_retry_count(at=retried_at)

    assert job.retry_count == 1
    assert job.updated_at == retried_at


def test_failed_job_requires_a_code_or_message_and_trims_failure_data():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    job.mark_running(at=NOW + timedelta(seconds=1))

    with pytest.raises(InvalidDocumentIngestionJob, match="failure code or message"):
        job.mark_failed(" ", " ", at=NOW + timedelta(seconds=2))

    job.mark_failed(" parse_failed ", " Safe summary ", at=NOW + timedelta(seconds=2))
    assert job.failure_code == "parse_failed"
    assert job.failure_message == "Safe summary"


def test_job_rejects_negative_retry_count_and_naive_timestamps():
    with pytest.raises(InvalidDocumentIngestionJob, match="retry count"):
        DocumentIngestionJob.create("document-1", retry_count=-1, created_at=NOW)
    with pytest.raises(InvalidDocumentIngestionJob, match="timezone-aware"):
        DocumentIngestionJob.create("document-1", created_at=datetime(2026, 7, 29))


def test_job_only_checkpoints_the_step_currently_being_attempted():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    job.mark_running(at=NOW + timedelta(seconds=1))
    job.set_current_step(IngestionStep.parse, at=NOW + timedelta(seconds=2))

    with pytest.raises(InvalidDocumentIngestionJob, match="currently attempted"):
        job.mark_step_completed(IngestionStep.chunk, at=NOW + timedelta(seconds=3))

    job.mark_step_completed(IngestionStep.parse, at=NOW + timedelta(seconds=3))
    assert job.last_completed_step is IngestionStep.parse
    assert job.current_step is IngestionStep.parse


def test_step_attempt_state_is_persistable_and_resets_only_when_step_advances():
    job = DocumentIngestionJob.create("document-1", created_at=NOW)
    job.mark_running(at=NOW + timedelta(seconds=1))
    job.set_current_step(IngestionStep.embed, at=NOW + timedelta(seconds=2))
    job.begin_step_attempt(at=NOW + timedelta(seconds=3))
    job.schedule_retry(
        "ingestion_timeout",
        "The ingestion operation timed out.",
        at=NOW + timedelta(seconds=4),
    )

    assert job.retry_count == 1
    assert job.current_step_attempt_count == 2
    assert job.failure_code == "ingestion_timeout"
    assert job.last_attempted_at == NOW + timedelta(seconds=4)

    job.set_current_step(IngestionStep.embed, at=NOW + timedelta(seconds=5))
    assert job.current_step_attempt_count == 2
    job.set_current_step(IngestionStep.persist, at=NOW + timedelta(seconds=6))
    assert job.current_step_attempt_count == 0
    assert job.failure_code is None
