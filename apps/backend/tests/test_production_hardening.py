import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from assistant.application.ingestion_service import IngestionService
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.knowledge_persistence import KnowledgePersistenceResult
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader
from assistant.infrastructure.repositories.ingestion_job import InMemoryIngestionJobRepository
from core.config import (
    AISettings,
    get_ai_settings,
    get_database_settings,
    get_website_loader_settings,
    validate_startup_configuration,
)
from core.health import DependencyHealthError, validate_dependency_health
from core.logging import JsonFormatter
from core.metrics import IngestionMetrics
from infrastructure.ai.client import create_ai_provider


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AI_MAX_RETRIES", "-1", "AI_MAX_RETRIES"),
        ("INGESTION_HTTP_RETRIES", "-1", "INGESTION_HTTP_RETRIES"),
        ("DATABASE_CONNECT_TIMEOUT_SECONDS", "0", "DATABASE_CONNECT_TIMEOUT_SECONDS"),
        ("DATABASE_OPERATION_TIMEOUT_SECONDS", "invalid", "DATABASE_OPERATION_TIMEOUT_SECONDS"),
    ],
)
def test_startup_validation_rejects_invalid_operational_limits(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        validate_startup_configuration()


def test_operational_retry_and_database_timeout_configuration_is_environment_driven(monkeypatch):
    monkeypatch.setenv("AI_MAX_RETRIES", "4")
    monkeypatch.setenv("INGESTION_HTTP_RETRIES", "3")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("DATABASE_OPERATION_TIMEOUT_SECONDS", "19.5")

    assert get_ai_settings().max_retries == 4
    assert get_website_loader_settings().max_retries == 3
    assert get_database_settings().connect_timeout_seconds == 7
    assert get_database_settings().operation_timeout_seconds == 19.5


def test_invalid_configuration_prevents_application_startup(monkeypatch):
    monkeypatch.setenv("INGESTION_MAX_PAGES", "0")
    from main import app

    with pytest.raises(ValueError, match="INGESTION_MAX_PAGES"):
        with TestClient(app):
            pass


def test_provider_factory_passes_validated_retry_limit_to_sdk_adapter():
    settings = AISettings(
        provider="openai",
        openai_api_key="test-key",
        openai_model="test-model",
        request_timeout=12,
        max_retries=5,
    )

    with patch("infrastructure.ai.client.OpenAIProvider") as provider_type:
        create_ai_provider(settings)

    provider_type.assert_called_once_with(
        api_key="test-key",
        model="test-model",
        timeout=12,
        max_retries=5,
        embedding_model="text-embedding-3-small",
    )


def test_json_formatter_emits_structured_fields_without_serialising_unapproved_values():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "Ingestion started", (), None)
    record.ingestion_job_id = "job-123"
    record.documents_processed = 2
    record.chunk_text = "must-not-leak"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "Ingestion started"
    assert payload["level"] == "INFO"
    assert payload["ingestion_job_id"] == "job-123"
    assert payload["documents_processed"] == 2
    assert "chunk_text" not in payload
    assert "must-not-leak" not in json.dumps(payload)


def test_json_formatter_removes_query_parameters_from_logged_urls():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "Website crawl started", (), None)
    record.source_url = "https://example.com/docs?api_key=must-not-leak#section"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["source_url"] == "https://example.com/docs"
    assert "must-not-leak" not in json.dumps(payload)


def test_ingestion_records_success_metrics_for_observable_pipeline_outcomes():
    registry = CollectorRegistry()
    metrics = IngestionMetrics(registry=registry)
    repository = InMemoryIngestionJobRepository()
    loader = SimpleNamespace(load=lambda _url: [object(), object()])
    processor = SimpleNamespace(
        process=lambda _documents: ContentProcessingResult(
            documents_received=2,
            documents_processed=1,
            documents_skipped=1,
            chunks_created=3,
            chunks=[],
            warnings=[],
            duration_ms=7,
        )
    )
    persistence = SimpleNamespace(
        persist=lambda _result: KnowledgePersistenceResult(
            documents_received=1,
            documents_created=1,
            documents_updated=0,
            documents_unchanged=0,
            chunks_received=3,
            chunks_created=3,
            chunks_updated=0,
            chunks_unchanged=0,
            chunks_removed=0,
            embeddings_generated=3,
            duration_ms=11,
            embedding_duration_ms=5,
            database_duration_ms=6,
        )
    )

    IngestionService(repository, loader, processor, persistence, metrics=metrics).start_ingestion(
        "https://example.com"
    )

    values = {
        sample.name: sample.value for metric in registry.collect() for sample in metric.samples
    }
    assert values["ingestion_success_total"] == 1
    assert values["ingestion_pages_processed_total"] == 1
    assert values["ingestion_pages_skipped_total"] == 1
    assert values["ingestion_documents_persisted_total"] == 1
    assert values["ingestion_chunks_persisted_total"] == 3
    assert values["ingestion_embeddings_generated_total"] == 3


def test_ingestion_records_failure_metric_without_exposing_exception_details():
    registry = CollectorRegistry()
    metrics = IngestionMetrics(registry=registry)
    repository = InMemoryIngestionJobRepository()

    class FailingLoader:
        def load(self, _url):
            raise RuntimeError("upstream credential")

    service = IngestionService(
        repository,
        FailingLoader(),
        SimpleNamespace(),
        SimpleNamespace(),
        metrics=metrics,
    )

    with pytest.raises(Exception, match="Knowledge ingestion failed") as raised:
        service.start_ingestion("https://example.com")

    values = {
        sample.name: sample.value for metric in registry.collect() for sample in metric.samples
    }
    assert values["ingestion_failure_total"] == 1
    assert "credential" not in str(raised.value)


def test_owned_website_client_is_closed_but_injected_client_is_not():
    injected = SimpleNamespace(close=lambda: pytest.fail("injected clients are caller-owned"))
    injected_loader = HttpWebsiteLoader(
        timeout_seconds=1,
        user_agent="test",
        max_pages=1,
        max_response_size=100,
        client=injected,
    )
    injected_loader.close()

    owned_loader = HttpWebsiteLoader(
        timeout_seconds=1,
        user_agent="test",
        max_pages=1,
        max_response_size=100,
    )
    with patch.object(owned_loader._client, "close") as close:
        owned_loader.close()
    close.assert_called_once_with()


def test_health_validation_checks_database_and_vector_extension(monkeypatch, tmp_path):
    executed: list[str] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            executed.append(query)

        def fetchone(self):
            return (True,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    validate_dependency_health(connection_factory=lambda: Connection())

    assert any("SELECT 1" in query for query in executed)
    assert any("pg_extension" in query for query in executed)


def test_health_validation_maps_missing_vector_extension_to_safe_error(monkeypatch, tmp_path):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

        def fetchone(self):
            return (False,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    with pytest.raises(DependencyHealthError, match="dependencies are unavailable") as raised:
        validate_dependency_health(connection_factory=lambda: Connection())

    assert "vector" not in str(raised.value).lower()


def test_failure_state_persistence_error_does_not_leak_infrastructure_exception():
    class Repository(InMemoryIngestionJobRepository):
        def update(self, job):
            if job.status.value == "failed":
                raise RuntimeError("database credentials")
            super().update(job)

    service = IngestionService(
        Repository(),
        SimpleNamespace(load=lambda _url: (_ for _ in ()).throw(RuntimeError("upstream secret"))),
        SimpleNamespace(),
        SimpleNamespace(),
        metrics=IngestionMetrics(registry=CollectorRegistry()),
    )

    with pytest.raises(Exception, match="Knowledge ingestion failed") as raised:
        service.start_ingestion("https://example.com")

    assert "credentials" not in str(raised.value)
    assert "secret" not in str(raised.value)


def test_job_creation_failure_is_mapped_and_counted_without_starting_external_work():
    class Repository(InMemoryIngestionJobRepository):
        def create(self, _job):
            raise RuntimeError("database hostname")

    calls = 0

    class Loader:
        def load(self, _url):
            nonlocal calls
            calls += 1

    registry = CollectorRegistry()
    service = IngestionService(
        Repository(),
        Loader(),
        SimpleNamespace(),
        SimpleNamespace(),
        metrics=IngestionMetrics(registry=registry),
    )

    with pytest.raises(Exception, match="Knowledge ingestion failed") as raised:
        service.start_ingestion("https://example.com")

    values = {
        sample.name: sample.value for metric in registry.collect() for sample in metric.samples
    }
    assert values["ingestion_failure_total"] == 1
    assert calls == 0
    assert "hostname" not in str(raised.value)


def test_job_completion_persistence_failure_is_mapped_after_successful_pipeline():
    class Repository(InMemoryIngestionJobRepository):
        def update(self, job):
            if job.status.value == "completed":
                raise RuntimeError("database hostname")
            super().update(job)

    registry = CollectorRegistry()
    service = IngestionService(
        Repository(),
        SimpleNamespace(load=lambda _url: [object()]),
        SimpleNamespace(
            process=lambda _documents: ContentProcessingResult(
                documents_received=1,
                documents_processed=1,
                documents_skipped=0,
                chunks_created=1,
                chunks=[],
                warnings=[],
                duration_ms=1,
            )
        ),
        SimpleNamespace(
            persist=lambda _result: KnowledgePersistenceResult(
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
                duration_ms=1,
            )
        ),
        metrics=IngestionMetrics(registry=registry),
    )

    with pytest.raises(Exception, match="Knowledge ingestion failed") as raised:
        service.start_ingestion("https://example.com")

    values = {
        sample.name: sample.value for metric in registry.collect() for sample in metric.samples
    }
    assert values["ingestion_failure_total"] == 1
    assert values.get("ingestion_success_total", 0) == 0
    assert "hostname" not in str(raised.value)
