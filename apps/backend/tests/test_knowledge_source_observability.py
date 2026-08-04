import logging
from unittest.mock import MagicMock, Mock

import pytest
from prometheus_client import CollectorRegistry

from assistant.application.knowledge_source_service import (
    ActiveIngestionConflict,
    IdempotencyConflict,
    KnowledgeSourceNotFound,
    KnowledgeSourceService,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource, KnowledgeSourceType
from core.metrics import KnowledgeSourceMetrics


def _counter(counter) -> float:
    return counter._value.get()


def _service(repository: Mock) -> tuple[KnowledgeSourceService, KnowledgeSourceMetrics]:
    assistants = Mock()
    assistants.get_by_id.return_value = object()
    metrics = KnowledgeSourceMetrics(registry=CollectorRegistry())
    return KnowledgeSourceService(repository, assistants, metrics), metrics


def test_success_logs_are_structured_and_exclude_sensitive_payloads(caplog):
    secret_text = "PRIVATE DIRECT TEXT SENTINEL"
    secret_html = "<main>PRIVATE HTML SENTINEL</main>"
    secret_chunk = "PRIVATE CHUNK SENTINEL"
    secret_embedding = "[0.123, 0.456]"
    secret_cookie = "redmoor_admin_session=PRIVATE COOKIE SENTINEL"
    secret_provider = "PRIVATE PROVIDER PAYLOAD SENTINEL"
    repository = MagicMock()
    transaction = repository.transaction.return_value.__enter__.return_value
    transaction.create.side_effect = lambda source, job, _hash, _key: (source, job)
    service, metrics = _service(repository)

    with caplog.at_level(logging.INFO):
        view, replayed = service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.direct_text,
            name="Private source",
            direct_text=secret_text,
        )

    assert replayed is False
    assert _counter(metrics.created) == 1
    record = next(
        record for record in caplog.records if record.message == "Knowledge source created"
    )
    assert record.assistant_id == str(REDMOOR_ASSISTANT_ID)
    assert record.source_id == str(view.source.id)
    assert record.document_id == view.source.document_id
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    for sensitive_value in (
        secret_text,
        secret_html,
        secret_chunk,
        secret_embedding,
        secret_cookie,
        secret_provider,
    ):
        assert sensitive_value not in rendered


def test_metrics_increment_only_after_successful_lifecycle_events():
    repository = MagicMock()
    transaction = repository.transaction.return_value.__enter__.return_value
    service, metrics = _service(repository)
    source = KnowledgeSource.create(
        assistant_id=REDMOOR_ASSISTANT_ID,
        source_type=KnowledgeSourceType.direct_text,
        name="Metrics",
        direct_text="Fictional metrics content.",
    )
    job = DocumentIngestionJob.create(source.document_id)

    transaction.create.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.direct_text,
            name="Metrics",
            direct_text="Fictional metrics content.",
        )
    assert _counter(metrics.created) == 0

    repository.get.return_value = source
    transaction.reingest.side_effect = IdempotencyConflict("conflict")
    with pytest.raises(IdempotencyConflict):
        service.reingest(REDMOOR_ASSISTANT_ID, source.id, idempotency_key="conflict")
    assert _counter(metrics.reingested) == 0
    assert _counter(metrics.replayed) == 0

    transaction.update_retrieval_state.return_value = None
    with pytest.raises(KnowledgeSourceNotFound):
        service.update(REDMOOR_ASSISTANT_ID, source.id, DocumentRetrievalState.disabled)
    assert _counter(metrics.retrieval_disabled) == 0

    transaction.delete.side_effect = ActiveIngestionConflict("active")
    with pytest.raises(ActiveIngestionConflict):
        service.delete(REDMOOR_ASSISTANT_ID, source.id)
    assert _counter(metrics.deleted) == 0

    transaction.reingest.side_effect = None
    transaction.reingest.return_value = (source, job, False)
    result, replayed = service.reingest(REDMOOR_ASSISTANT_ID, source.id)
    assert result.latest_job == job
    assert replayed is False
    assert _counter(metrics.reingested) == 1

    transaction.update_retrieval_state.return_value = source
    repository.latest_job.return_value = job
    service.update(REDMOOR_ASSISTANT_ID, source.id, DocumentRetrievalState.disabled)
    assert _counter(metrics.retrieval_disabled) == 1

    transaction.delete.side_effect = None
    transaction.delete.return_value = True
    service.delete(REDMOOR_ASSISTANT_ID, source.id)
    assert _counter(metrics.deleted) == 1
