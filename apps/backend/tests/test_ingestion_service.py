import logging
from unittest.mock import Mock

import pytest

from assistant.application.ingestion_service import IngestionFailedError, IngestionService
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.ingestion_job import IngestionJob
from assistant.domain.ingestion_status import IngestionStatus
from assistant.domain.knowledge_persistence import KnowledgePersistenceResult
from assistant.infrastructure.repositories.ingestion_job import InMemoryIngestionJobRepository


class WriteFailure(RuntimeError):
    pass


class FaultInjectingJobRepository(InMemoryIngestionJobRepository):
    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure
        self.events: list[str] = []

    def create(self, job: IngestionJob) -> None:
        self.events.append("create")
        if self.failure == "create_before":
            raise WriteFailure("sensitive create failure")
        super().create(job)
        if self.failure == "create_after":
            self.failure = ""
            raise WriteFailure("sensitive ambiguous create failure")

    def update(self, job: IngestionJob) -> None:
        event = f"update_{job.status.value}"
        self.events.append(event)
        if self.failure == "failed_state" and job.status is IngestionStatus.failed:
            raise WriteFailure("sensitive failed-state failure")
        if self.failure == f"{event}_before":
            self.failure = ""
            raise WriteFailure(f"sensitive {event} failure")
        super().update(job)
        if self.failure == f"{event}_after":
            self.failure = ""
            raise WriteFailure(f"sensitive ambiguous {event} failure")


def successful_service(repository: FaultInjectingJobRepository):
    loader = Mock()
    loader.load.return_value = [object()]
    processor = Mock()
    processor.process.return_value = ContentProcessingResult(
        documents_received=1,
        documents_processed=1,
        documents_skipped=0,
        chunks_created=1,
        chunks=[],
        warnings=[],
        duration_ms=2,
    )
    persistence = Mock()
    prepared = object()
    persistence.prepare.return_value = prepared
    persistence.persist_prepared.return_value = KnowledgePersistenceResult(
        documents_received=1,
        documents_created=1,
        documents_updated=0,
        documents_unchanged=0,
        chunks_received=1,
        chunks_created=1,
        chunks_updated=0,
        chunks_unchanged=0,
        chunks_removed=0,
        embeddings_generated=1,
        duration_ms=3,
    )
    return IngestionService(repository, loader, processor, persistence), loader, persistence


def only_job(repository: InMemoryIngestionJobRepository) -> IngestionJob | None:
    return repository.latest()


def test_pending_job_creation_failure_does_not_run_pipeline_or_invent_a_job():
    repository = FaultInjectingJobRepository("create_before")
    service, loader, persistence = successful_service(repository)

    with pytest.raises(IngestionFailedError) as raised:
        service.start_ingestion("https://example.com/knowledge")

    assert isinstance(raised.value.__cause__, WriteFailure)
    assert only_job(repository) is None
    loader.load.assert_not_called()
    persistence.prepare.assert_not_called()


def test_ambiguous_pending_create_is_reloaded_and_pipeline_completes_once():
    repository = FaultInjectingJobRepository("create_after")
    service, loader, persistence = successful_service(repository)

    result = service.start_ingestion("https://example.com/knowledge")

    assert result.status is IngestionStatus.completed
    assert only_job(repository) == result
    loader.load.assert_called_once_with("https://example.com/knowledge")
    persistence.persist_prepared.assert_called_once()


def test_running_state_failure_persists_failed_job_and_stops_before_pipeline():
    repository = FaultInjectingJobRepository("update_running_before")
    service, loader, persistence = successful_service(repository)

    with pytest.raises(IngestionFailedError) as raised:
        service.start_ingestion("https://example.com/knowledge")

    assert isinstance(raised.value.__cause__, WriteFailure)
    stored = only_job(repository)
    assert stored is not None
    assert stored.status is IngestionStatus.failed
    assert stored.error_message == "Ingestion job initialization failed."
    loader.load.assert_not_called()
    persistence.prepare.assert_not_called()


def test_ambiguous_running_update_is_reloaded_and_pipeline_completes_once():
    repository = FaultInjectingJobRepository("update_running_after")
    service, loader, persistence = successful_service(repository)

    result = service.start_ingestion("https://example.com/knowledge")

    assert result.status is IngestionStatus.completed
    assert only_job(repository) == result
    loader.load.assert_called_once()
    persistence.persist_prepared.assert_called_once()


def test_completion_update_failure_marks_durable_running_job_failed_without_repersisting_knowledge():
    repository = FaultInjectingJobRepository("update_completed_before")
    service, loader, persistence = successful_service(repository)

    with pytest.raises(IngestionFailedError) as raised:
        service.start_ingestion("https://example.com/knowledge")

    assert isinstance(raised.value.__cause__, WriteFailure)
    stored = only_job(repository)
    assert stored is not None
    assert stored.status is IngestionStatus.failed
    assert stored.error_message == "Ingestion completion state could not be persisted."
    loader.load.assert_called_once()
    persistence.persist_prepared.assert_called_once()


def test_ambiguous_completion_update_returns_confirmed_durable_completion():
    repository = FaultInjectingJobRepository("update_completed_after")
    service, loader, persistence = successful_service(repository)

    result = service.start_ingestion("https://example.com/knowledge")

    assert result.status is IngestionStatus.completed
    assert result.documents_discovered == 1
    assert result.documents_processed == 1
    assert result.chunks_created == 1
    assert only_job(repository) == result
    loader.load.assert_called_once()
    persistence.persist_prepared.assert_called_once()
    assert "update_failed" not in repository.events


def test_secondary_failed_state_write_is_logged_but_original_completion_failure_remains_primary(
    caplog,
):
    repository = FaultInjectingJobRepository("update_completed_before")
    service, _loader, persistence = successful_service(repository)
    original_update = repository.update

    def fail_completion_and_failed_state(job: IngestionJob) -> None:
        if job.status is IngestionStatus.failed:
            raise WriteFailure("sensitive secondary failure")
        original_update(job)

    repository.update = fail_completion_and_failed_state  # type: ignore[method-assign]

    with caplog.at_level(logging.ERROR), pytest.raises(IngestionFailedError) as raised:
        service.start_ingestion("https://example.com/knowledge")

    assert isinstance(raised.value.__cause__, WriteFailure)
    assert "update_completed failure" in str(raised.value.__cause__)
    stored = only_job(repository)
    assert stored is not None
    assert stored.status is IngestionStatus.running
    persistence.persist_prepared.assert_called_once()
    assert "Ingestion failure state could not be persisted" in caplog.text


def test_pipeline_failure_remains_primary_when_failed_state_cannot_be_persisted(caplog):
    repository = FaultInjectingJobRepository("failed_state")
    service, loader, persistence = successful_service(repository)
    loader.load.side_effect = RuntimeError("sensitive website failure")

    with caplog.at_level(logging.ERROR), pytest.raises(IngestionFailedError) as raised:
        service.start_ingestion("https://example.com/knowledge")

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert str(raised.value.__cause__) == "sensitive website failure"
    stored = only_job(repository)
    assert stored is not None
    assert stored.status is IngestionStatus.running
    persistence.prepare.assert_not_called()
    assert "Ingestion failure state could not be persisted" in caplog.text


def test_ingestion_logs_only_safe_source_origin(caplog):
    repository = FaultInjectingJobRepository("")
    service, _loader, _persistence = successful_service(repository)
    source_url = "https://example.com/private/path-secret?token=query-secret#fragment-secret"

    with caplog.at_level(logging.INFO):
        result = service.start_ingestion(source_url)

    assert result.status is IngestionStatus.completed
    started = next(
        record for record in caplog.records if record.getMessage() == "Ingestion job started"
    )
    assert started.source == "https://example.com"
    assert "path-secret" not in caplog.text
    assert "query-secret" not in caplog.text
    assert "fragment-secret" not in caplog.text
