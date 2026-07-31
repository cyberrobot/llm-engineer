from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from assistant.api.dependencies import (
    get_document_ingestion_job_service,
    get_ingestion_operational_status_repository,
    get_ingestion_pipeline_runner,
    get_ingestion_step_execution_repository,
)
from assistant.application.ingestion_job_service import DocumentIngestionJobService
from assistant.application.ingestion_observability import IngestionOperationalStatus
from assistant.application.ingestion_pipeline import IngestionPipelineResult
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)
from assistant.infrastructure.repositories.ingestion_observability import (
    InMemoryIngestionStepExecutionRepository,
)


@pytest.fixture
def client_and_documents(monkeypatch) -> Iterator[tuple[TestClient, set[str]]]:
    from main import app

    monkeypatch.setenv("INGEST_API_KEY", "test-ingestion-key")
    documents = {str(uuid4()), str(uuid4())}
    repository = InMemoryDocumentIngestionJobRepository(document_ids=documents)
    service = DocumentIngestionJobService(repository)
    executions = InMemoryIngestionStepExecutionRepository()
    app.dependency_overrides[get_document_ingestion_job_service] = lambda: service
    app.dependency_overrides[get_ingestion_step_execution_repository] = lambda: executions
    yield TestClient(app, headers={"X-API-Key": "test-ingestion-key"}), documents
    app.dependency_overrides.pop(get_document_ingestion_job_service, None)
    app.dependency_overrides.pop(get_ingestion_step_execution_repository, None)


def test_create_get_and_list_ingestion_jobs(client_and_documents):
    client, documents = client_and_documents
    document_id = next(iter(documents))

    created_response = client.post("/ingestion/jobs", json={"document_id": document_id})
    created = created_response.json()

    assert created_response.status_code == 202
    assert set(created) == {
        "id",
        "document_id",
        "status",
        "current_step",
        "last_completed_step",
        "retry_count",
        "current_step_attempt_count",
        "last_attempted_at",
        "failure_code",
        "failure_message",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
        "queued_at",
        "completed_step_count",
        "total_step_count",
        "progress_percent",
        "queue_wait_duration_ms",
        "processing_duration_ms",
        "total_duration_ms",
        "failure",
    }
    UUID(created["id"])
    assert created["document_id"] == document_id
    assert created["status"] == "queued"
    assert created["retry_count"] == 0
    assert created["current_step"] is None
    assert created["completed_step_count"] == 0
    assert created["total_step_count"] == 4
    assert created["progress_percent"] == 0
    assert created["queued_at"] == created["created_at"]
    assert created["queue_wait_duration_ms"] is None
    assert created["processing_duration_ms"] is None
    assert created["total_duration_ms"] >= 0
    assert created["failure"] is None
    assert datetime.fromisoformat(created["created_at"]).tzinfo is not None
    retrieved = client.get(f"/ingestion/jobs/{created['id']}").json()
    assert {key: value for key, value in retrieved.items() if key != "total_duration_ms"} == {
        key: value for key, value in created.items() if key != "total_duration_ms"
    }
    assert retrieved["total_duration_ms"] >= created["total_duration_ms"]

    listed = client.get("/ingestion/jobs", params={"document_id": document_id}).json()
    assert listed["total"] == 1
    assert listed["limit"] == 50
    assert listed["offset"] == 0
    assert [item["id"] for item in listed["items"]] == [created["id"]]


def test_idempotent_creation_and_conflict(client_and_documents):
    client, documents = client_and_documents
    first, second = documents
    headers = {"Idempotency-Key": "request-123"}

    first_response = client.post("/ingestion/jobs", json={"document_id": first}, headers=headers)
    repeated = client.post("/ingestion/jobs", json={"document_id": first}, headers=headers)
    conflict = client.post("/ingestion/jobs", json={"document_id": second}, headers=headers)

    assert first_response.status_code == repeated.status_code == 202
    assert repeated.json()["id"] == first_response.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"
    assert client.get("/ingestion/jobs").json()["total"] == 1


def test_api_validates_ids_filters_pagination_and_unknown_records(client_and_documents):
    client, documents = client_and_documents

    assert client.post("/ingestion/jobs", json={"document_id": str(uuid4())}).status_code == 404
    assert client.post("/ingestion/jobs", json={"document_id": "bad"}).status_code == 422
    assert client.get("/ingestion/jobs/not-a-uuid").status_code == 422
    missing = client.get(f"/ingestion/jobs/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "ingestion_job_not_found"
    assert client.get("/ingestion/jobs", params={"status": "invalid"}).status_code == 422
    assert client.get("/ingestion/jobs", params={"limit": 0}).status_code == 422
    invalid_range = client.get(
        "/ingestion/jobs",
        params={"created_from": "2026-08-01T00:00:00Z", "created_to": "2026-07-01T00:00:00Z"},
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["detail"]["code"] == "invalid_created_range"

    document_id = next(iter(documents))
    created = client.post("/ingestion/jobs", json={"document_id": document_id}).json()
    filtered = client.get("/ingestion/jobs", params={"status": "queued", "limit": 1}).json()
    assert [item["id"] for item in filtered["items"]] == [created["id"]]
    assert filtered["items"][0]["status"] == "queued"
    assert filtered["total"] == 1


def test_run_ingestion_job_returns_structured_synchronous_result(monkeypatch):
    from main import app

    monkeypatch.setenv("INGEST_API_KEY", "test-ingestion-key")
    job_id = uuid4()

    class Runner:
        def run(self, requested_job_id):
            assert requested_job_id == job_id
            return IngestionPipelineResult(
                job_id,
                IngestionStatus.completed,
                True,
                last_completed_step=IngestionStep.persist,
            )

    app.dependency_overrides[get_ingestion_pipeline_runner] = lambda: Runner()
    try:
        response = TestClient(app).post(
            f"/ingestion/jobs/{job_id}/run", headers={"X-API-Key": "test-ingestion-key"}
        )
    finally:
        app.dependency_overrides.pop(get_ingestion_pipeline_runner, None)

    assert response.status_code == 200
    assert response.json() == {
        "job_id": str(job_id),
        "status": "completed",
        "succeeded": True,
        "last_completed_step": "persist",
        "failed_step": None,
        "failure_code": None,
        "failure_message": None,
        "retryable": None,
        "attempts_used": 0,
        "retries_performed": 0,
        "retry_exhausted": False,
        "total_retries": 0,
    }


def test_step_history_is_scoped_to_an_existing_parent_job(client_and_documents):
    client, documents = client_and_documents
    document_id = next(iter(documents))
    job_id = client.post("/ingestion/jobs", json={"document_id": document_id}).json()["id"]

    response = client.get(f"/ingestion/jobs/{job_id}/steps")

    assert response.status_code == 200
    assert response.json() == []
    missing = client.get(f"/ingestion/jobs/{uuid4()}/steps")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "ingestion_job_not_found"


def test_ingestion_job_status_and_history_reject_unauthenticated_access(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "configured-secret")
    from main import app

    client = TestClient(app)
    assert client.get("/ingestion/jobs").status_code == 401
    assert client.get(f"/ingestion/jobs/{uuid4()}").status_code == 401
    assert client.get(f"/ingestion/jobs/{uuid4()}/steps").status_code == 401


def test_internal_ingestion_status_is_api_key_protected(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "configured-secret")
    from main import app

    class StatusRepository:
        def get(self, *, now):
            assert now.tzinfo is not None
            return IngestionOperationalStatus(12, 3, 1, 84.0, 2)

    app.dependency_overrides[get_ingestion_operational_status_repository] = StatusRepository
    try:
        client = TestClient(app)
        assert client.get("/internal/ingestion/status").status_code == 401
        response = client.get(
            "/internal/ingestion/status", headers={"X-API-Key": "configured-secret"}
        )
    finally:
        app.dependency_overrides.pop(get_ingestion_operational_status_repository, None)

    assert response.status_code == 200
    assert response.json() == {
        "queued_jobs": 12,
        "running_jobs": 3,
        "recoverable_jobs": 1,
        "oldest_queued_age_seconds": 84.0,
        "workers_observed": 2,
    }
