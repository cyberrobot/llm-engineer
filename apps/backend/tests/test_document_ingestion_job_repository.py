from datetime import datetime, timedelta, timezone
from uuid import uuid4

from assistant.domain.document_ingestion_job import DocumentIngestionJob, IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
    PostgresDocumentIngestionJobRepository,
)


def test_repository_lists_newest_first_with_pagination_and_filters():
    first_document = str(uuid4())
    second_document = str(uuid4())
    repository = InMemoryDocumentIngestionJobRepository(
        document_ids={first_document, second_document}
    )
    timestamp = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
    oldest = DocumentIngestionJob.create(first_document, created_at=timestamp)
    newest = DocumentIngestionJob.create(
        second_document, created_at=timestamp + timedelta(seconds=1)
    )
    repository.create(oldest)
    repository.create(newest)

    first_page = repository.list(limit=1, offset=0)
    second_page = repository.list(limit=1, offset=1)
    filtered = repository.list(
        limit=10, offset=0, status=IngestionStatus.queued, document_id=first_document
    )

    assert first_page.total == second_page.total == 2
    assert first_page.items == [newest]
    assert second_page.items == [oldest]
    assert filtered.items == [oldest]
    assert filtered.total == 1


def test_postgres_row_mapping_preserves_enums_nullable_fields_and_timestamps():
    timestamp = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
    job_id = uuid4()

    job = PostgresDocumentIngestionJobRepository._from_row(
        (
            str(job_id),
            str(uuid4()),
            "queued",
            None,
            0,
            None,
            None,
            None,
            timestamp,
            None,
            None,
            timestamp,
        )
    )

    assert job.id == job_id
    assert job.status is IngestionStatus.queued
    assert job.current_step is None
    assert job.started_at is None
    assert job.completed_at is None


def test_in_memory_repository_persists_domain_state_updates_as_snapshots():
    document_id = str(uuid4())
    repository = InMemoryDocumentIngestionJobRepository(document_ids={document_id})
    job = DocumentIngestionJob.create(document_id)
    repository.create(job)

    job.mark_running()
    job.set_current_step(IngestionStep.parse)
    repository.update(job)
    job.set_current_step(IngestionStep.chunk)

    stored = repository.get_by_id(job.id)
    assert stored is not None
    assert stored.status is IngestionStatus.running
    assert stored.current_step is IngestionStep.parse
