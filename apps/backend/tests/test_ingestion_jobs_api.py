from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from assistant.api.dependencies import (
    get_document_ingestion_job_service,
    get_ingestion_pipeline_runner,
)
from assistant.application.ingestion_job_service import DocumentIngestionJobService
from assistant.application.ingestion_pipeline import IngestionPipelineResult
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.document_ingestion_job import (
    InMemoryDocumentIngestionJobRepository,
)


@pytest.fixture
def client_and_documents() -> Iterator[tuple[TestClient, set[str]]]:
    from main import app

    documents = {str(uuid4()), str(uuid4())}
    repository = InMemoryDocumentIngestionJobRepository(document_ids=documents)
    service = DocumentIngestionJobService(repository)
    app.dependency_overrides[get_document_ingestion_job_service] = lambda: service
    yield TestClient(app), documents
    app.dependency_overrides.pop(get_document_ingestion_job_service, None)


def test_create_get_and_list_ingestion_jobs(client_and_documents):
    client, documents = client_and_documents
    document_id = next(iter(documents))

    created_response = client.post("/ingestion/jobs", json={"document_id": document_id})
    created = created_response.json()

    assert created_response.status_code == 201
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
    }
    UUID(created["id"])
    assert created["document_id"] == document_id
    assert created["status"] == "queued"
    assert created["retry_count"] == 0
    assert created["current_step"] is None
    assert datetime.fromisoformat(created["created_at"]).tzinfo is not None
    assert client.get(f"/ingestion/jobs/{created['id']}").json() == created

    listed = client.get("/ingestion/jobs", params={"document_id": document_id}).json()
    assert listed == {"items": [created], "total": 1, "limit": 50, "offset": 0}


def test_idempotent_creation_and_conflict(client_and_documents):
    client, documents = client_and_documents
    first, second = documents
    headers = {"Idempotency-Key": "request-123"}

    first_response = client.post("/ingestion/jobs", json={"document_id": first}, headers=headers)
    repeated = client.post("/ingestion/jobs", json={"document_id": first}, headers=headers)
    conflict = client.post("/ingestion/jobs", json={"document_id": second}, headers=headers)

    assert first_response.status_code == repeated.status_code == 201
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

    document_id = next(iter(documents))
    created = client.post("/ingestion/jobs", json={"document_id": document_id}).json()
    filtered = client.get("/ingestion/jobs", params={"status": "queued", "limit": 1}).json()
    assert filtered["items"] == [created]
    assert filtered["total"] == 1


def test_run_ingestion_job_returns_structured_synchronous_result():
    from main import app

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
        response = TestClient(app).post(f"/ingestion/jobs/{job_id}/run")
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
