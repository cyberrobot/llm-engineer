from datetime import datetime, timedelta, timezone

from assistant.domain.ingestion_job import IngestionJob
from assistant.infrastructure.repositories.ingestion_job import InMemoryIngestionJobRepository


def test_repository_creates_and_retrieves_a_persisted_job_snapshot():
    repository = InMemoryIngestionJobRepository()
    job = IngestionJob.create("https://example.com/one")

    repository.create(job)
    job.start()

    stored = repository.get(job.id)

    assert stored is not None
    assert stored.status.value == "pending"
    assert stored.source_url == "https://example.com/one"


def test_repository_updates_an_existing_job_and_reloads_final_state():
    repository = InMemoryIngestionJobRepository()
    job = IngestionJob.create("https://example.com")
    repository.create(job)
    job.start()
    job.complete(documents_discovered=2, documents_processed=2, chunks_created=5)

    repository.update(job)

    stored = repository.get(job.id)
    assert stored is not None
    assert stored.status.value == "completed"
    assert stored.documents_processed == 2
    assert stored.chunks_created == 5
    assert stored.completed_at is not None


def test_repository_returns_none_for_an_unknown_job():
    repository = InMemoryIngestionJobRepository()
    unknown = IngestionJob.create("https://example.com")

    assert repository.get(unknown.id) is None


def test_repository_returns_the_most_recent_job_by_creation_time():
    repository = InMemoryIngestionJobRepository()
    first_time = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
    first = IngestionJob.create("https://example.com/first", created_at=first_time)
    second = IngestionJob.create(
        "https://example.com/second", created_at=first_time + timedelta(seconds=1)
    )
    repository.create(second)
    repository.create(first)

    latest = repository.latest()

    assert latest is not None
    assert latest.id == second.id


def test_empty_repository_has_no_latest_job():
    assert InMemoryIngestionJobRepository().latest() is None
