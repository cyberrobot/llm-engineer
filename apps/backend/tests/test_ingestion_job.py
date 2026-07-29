from datetime import datetime, timedelta, timezone

import pytest

from assistant.domain.ingestion_job import IngestionJob, InvalidIngestionJob
from assistant.domain.ingestion_status import IngestionStatus


def test_job_moves_from_pending_to_running_to_completed_with_counts_and_timestamps():
    created_at = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
    started_at = created_at + timedelta(seconds=1)
    completed_at = started_at + timedelta(seconds=2)
    job = IngestionJob.create("https://example.com/knowledge", created_at=created_at)

    job.start(at=started_at)
    job.complete(
        documents_discovered=3,
        documents_processed=2,
        chunks_created=8,
        at=completed_at,
    )

    assert job.status is IngestionStatus.completed
    assert job.documents_discovered == 3
    assert job.documents_processed == 2
    assert job.chunks_created == 8
    assert job.error_message is None
    assert job.started_at == started_at
    assert job.completed_at == completed_at


def test_completed_job_cannot_restart_or_fail():
    job = IngestionJob.create("https://example.com")
    job.start()
    job.complete(documents_discovered=0, documents_processed=0, chunks_created=0)

    with pytest.raises(InvalidIngestionJob, match="completed job"):
        job.start()
    with pytest.raises(InvalidIngestionJob, match="completed job"):
        job.fail("late failure")


def test_pending_job_cannot_complete_without_starting():
    job = IngestionJob.create("https://example.com")

    with pytest.raises(InvalidIngestionJob, match="running job"):
        job.complete(documents_discovered=0, documents_processed=0, chunks_created=0)


def test_failed_job_requires_a_non_empty_error_and_records_terminal_timestamp():
    failed_at = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
    job = IngestionJob.create("https://example.com", created_at=failed_at - timedelta(seconds=1))

    with pytest.raises(InvalidIngestionJob, match="error message"):
        job.fail("  ")

    job.fail("  source unavailable  ", at=failed_at)

    assert job.status is IngestionStatus.failed
    assert job.error_message == "source unavailable"
    assert job.completed_at == failed_at


@pytest.mark.parametrize(
    ("documents_discovered", "documents_processed", "chunks_created"),
    [(-1, 0, 0), (0, -1, 0), (0, 0, -1), (1, 2, 0)],
)
def test_completion_rejects_impossible_counts(
    documents_discovered, documents_processed, chunks_created
):
    job = IngestionJob.create("https://example.com")
    job.start()

    with pytest.raises(InvalidIngestionJob, match="counts"):
        job.complete(
            documents_discovered=documents_discovered,
            documents_processed=documents_processed,
            chunks_created=chunks_created,
        )


def test_job_rejects_naive_lifecycle_timestamps():
    with pytest.raises(InvalidIngestionJob, match="timezone-aware"):
        IngestionJob.create("https://example.com", created_at=datetime(2026, 7, 29))


def test_rehydrated_completed_job_requires_start_and_completion_timestamps():
    created_at = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(InvalidIngestionJob, match="completed job requires"):
        IngestionJob(
            id=IngestionJob.create("https://example.com").id,
            source_url="https://example.com",
            status=IngestionStatus.completed,
            documents_discovered=0,
            documents_processed=0,
            chunks_created=0,
            error_message=None,
            created_at=created_at,
            started_at=None,
            completed_at=None,
        )


def test_rehydrated_failed_job_requires_an_error_message():
    terminal_at = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(InvalidIngestionJob, match="failed job requires an error message"):
        IngestionJob(
            id=IngestionJob.create("https://example.com").id,
            source_url="https://example.com",
            status=IngestionStatus.failed,
            documents_discovered=0,
            documents_processed=0,
            chunks_created=0,
            error_message=None,
            created_at=terminal_at - timedelta(seconds=1),
            started_at=None,
            completed_at=terminal_at,
        )
