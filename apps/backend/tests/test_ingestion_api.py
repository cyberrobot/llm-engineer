from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from assistant.api.dependencies import get_ingestion_service
from assistant.application.ingestion_service import IngestionService
from assistant.domain.ingestion_job import IngestionJob
from assistant.infrastructure.repositories.ingestion_job import InMemoryIngestionJobRepository


@pytest.fixture
def ingestion_client() -> Iterator[tuple[TestClient, InMemoryIngestionJobRepository]]:
    from main import app

    repository = InMemoryIngestionJobRepository()
    app.dependency_overrides[get_ingestion_service] = lambda: IngestionService(repository)
    yield TestClient(app), repository
    app.dependency_overrides.pop(get_ingestion_service, None)


def test_start_ingestion_creates_and_returns_a_completed_zero_result_job(ingestion_client):
    client, repository = ingestion_client

    response = client.post(
        "/assistant/knowledge/ingestions", json={"url": "https://example.com/knowledge"}
    )

    assert response.status_code == 201
    body = response.json()
    UUID(body["jobId"])
    assert body["status"] == "completed"
    assert body["sourceUrl"] == "https://example.com/knowledge"
    assert body["documentsDiscovered"] == 0
    assert body["documentsProcessed"] == 0
    assert body["chunksCreated"] == 0
    assert body["error"] is None
    assert datetime.fromisoformat(body["createdAt"]).tzinfo is not None
    assert datetime.fromisoformat(body["startedAt"]).tzinfo is not None
    assert datetime.fromisoformat(body["completedAt"]).tzinfo is not None

    stored = repository.get(UUID(body["jobId"]))
    assert stored is not None
    assert stored.status.value == "completed"


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "data:text/plain,hello",
        "https://user:secret@example.com/private",
    ],
)
def test_start_ingestion_rejects_invalid_or_credentialed_urls_without_creating_a_job(
    ingestion_client, url
):
    client, repository = ingestion_client

    response = client.post("/assistant/knowledge/ingestions", json={"url": url})

    assert response.status_code == 422
    assert repository.latest() is None


def test_start_ingestion_rejects_missing_url_without_creating_a_job(ingestion_client):
    client, repository = ingestion_client

    response = client.post("/assistant/knowledge/ingestions", json={})

    assert response.status_code == 422
    assert repository.latest() is None


def test_get_ingestion_returns_the_existing_job(ingestion_client):
    client, _repository = ingestion_client
    created = client.post(
        "/assistant/knowledge/ingestions", json={"url": "http://example.com/docs"}
    ).json()

    response = client.get(f"/assistant/knowledge/ingestions/{created['jobId']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_ingestion_returns_404_for_an_unknown_job(ingestion_client):
    client, _repository = ingestion_client

    response = client.get(f"/assistant/knowledge/ingestions/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ingestion job not found."}


def test_knowledge_status_is_empty_when_no_job_exists(ingestion_client):
    client, _repository = ingestion_client

    response = client.get("/assistant/knowledge/status")

    assert response.status_code == 200
    assert response.json() == {
        "documents": 0,
        "chunks": 0,
        "lastIngestionAt": None,
        "lastIngestionStatus": None,
    }


def test_knowledge_status_reflects_the_latest_completed_job(ingestion_client):
    client, repository = ingestion_client
    job = IngestionJob.create("https://example.com")
    job.start()
    job.complete(documents_discovered=3, documents_processed=2, chunks_created=7)
    repository.create(job)

    response = client.get("/assistant/knowledge/status")

    assert response.status_code == 200
    assert response.json() == {
        "documents": 2,
        "chunks": 7,
        "lastIngestionAt": job.completed_at.isoformat().replace("+00:00", "Z"),
        "lastIngestionStatus": "completed",
    }
