from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assistant.api.file_dependencies import get_file_fingerprint_service, get_file_ingestion_service
from assistant.api.ingest import router
from assistant.application.file_fingerprint import FileFingerprintService
from assistant.application.file_ingestion import FileIngestionResult, FileIngestionService
from assistant.domain.file_fingerprint import ContentStatus
from assistant.domain.ingestion_status import IngestionStatus
from assistant.infrastructure.repositories.file_ingestion import InMemoryFileIngestionRepository
from shared.dependencies.rate_limit import limiter

client_counter = 0


@pytest.fixture(autouse=True)
def disable_rate_limit_for_upload_tests():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def make_client(*, ingestion_result: FileIngestionResult | None = None):
    global client_counter
    client_counter += 1
    app = FastAPI()
    app.include_router(router)
    if ingestion_result is not None:
        service = Mock()
        service.submit.return_value = ingestion_result
        app.dependency_overrides[get_file_ingestion_service] = lambda: service
        app.state.file_ingestion_service = service
    return TestClient(app, client=(f"testclient-{client_counter}", 50000))


def post_upload(client, filename="policy.pdf", content_type="application/pdf", content=b"%PDF-1.7"):
    return client.post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user,admin"},
        files={"file": (filename, content, content_type)},
        headers={"X-API-Key": "test-key"},
    )


def test_successful_pdf_upload_creates_document_job_and_returns_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "25")

    result = FileIngestionResult(
        "doc-id",
        UUID("00000000-0000-0000-0000-000000000009"),
        ContentStatus.new_content,
        False,
        True,
        False,
        False,
    )
    client = make_client(ingestion_result=result)
    with patch("assistant.api.ingest.uuid.uuid4", return_value="upload-id"):
        response = post_upload(client)

    assert response.status_code == 202
    assert response.json() == {
        "document_id": "doc-id",
        "job_id": "00000000-0000-0000-0000-000000000009",
        "ingestion_job_id": "00000000-0000-0000-0000-000000000009",
        "filename": "policy.pdf",
        "status": "queued",
        "next_stage": "validate",
        "content_status": "NEW_CONTENT",
        "deduplicated": False,
        "ingestion_required": True,
        "ingestion_in_progress": False,
        "force_reindex": False,
    }
    assert (tmp_path / "upload-id.pdf").read_bytes() == b"%PDF-1.7"
    submitted = client.app.state.file_ingestion_service.submit.call_args.args[0]
    assert submitted.original_filename == "policy.pdf"
    assert submitted.access_roles == ("user", "admin")
    assert submitted.fingerprint.file_size_bytes == len(b"%PDF-1.7")
    assert (
        submitted.fingerprint.checksum
        == "86edbaa24831badfa0a8b04bb410141e2ee4182b6d0014493fe262a7a331c20b"
    )
    assert submitted.upload_path == str(tmp_path / "upload-id.pdf")


def test_completed_duplicate_returns_200_without_exposing_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    result = FileIngestionResult(
        "canonical-document",
        UUID("00000000-0000-0000-0000-000000000010"),
        ContentStatus.duplicate_content,
        True,
        False,
        False,
        False,
    )

    response = post_upload(make_client(ingestion_result=result), filename="renamed.pdf")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "canonical-document"
    assert body["content_status"] == "DUPLICATE_CONTENT"
    assert body["deduplicated"] is True
    assert body["ingestion_required"] is False
    assert "checksum" not in body


def test_repeated_upload_reuses_active_job_and_force_reindex_creates_job_after_completion(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    repository = InMemoryFileIngestionRepository()
    service = FileIngestionService(repository)
    client = make_client()
    client.app.dependency_overrides[get_file_ingestion_service] = lambda: service

    created = post_upload(client, filename="first.pdf")
    active_duplicate = post_upload(client, filename="renamed.pdf")
    forced_while_active = client.post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user,admin", "force_reindex": "true"},
        files={"file": ("forced.pdf", b"%PDF-1.7", "application/pdf")},
        headers={"X-API-Key": "test-key"},
    )

    assert created.status_code == 202
    assert active_duplicate.status_code == 200
    assert active_duplicate.json()["document_id"] == created.json()["document_id"]
    assert active_duplicate.json()["job_id"] == created.json()["job_id"]
    assert active_duplicate.json()["ingestion_in_progress"] is True
    assert forced_while_active.status_code == 200
    assert repository.document_count == 1
    assert repository.job_count == 1

    repository.set_job_status(UUID(created.json()["job_id"]), IngestionStatus.completed)
    forced = client.post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user,admin", "force_reindex": "true"},
        files={"file": ("forced.pdf", b"%PDF-1.7", "application/pdf")},
        headers={"X-API-Key": "test-key"},
    )

    assert forced.status_code == 202
    assert forced.json()["content_status"] == "FORCED_REINDEX"
    assert forced.json()["document_id"] == created.json()["document_id"]
    assert forced.json()["job_id"] != created.json()["job_id"]
    assert repository.document_count == 1
    assert repository.job_count == 2


def test_missing_file_rejected(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    response = make_client().post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user"},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "PDF file is required."


def test_non_pdf_extension_rejected(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    response = post_upload(make_client(), filename="policy.txt")

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file must have a .pdf extension."


def test_invalid_content_type_rejected(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    response = post_upload(make_client(), content_type="text/plain")

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file content type must be application/pdf."


def test_oversized_upload_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")

    service = Mock()
    client = make_client()
    client.app.dependency_overrides[get_file_ingestion_service] = lambda: service
    with patch("assistant.api.ingest.uuid.uuid4", return_value="upload-id"):
        response = post_upload(client)

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file exceeds maximum size."
    assert not (tmp_path / "upload-id.pdf").exists()
    service.submit.assert_not_called()


def test_fingerprint_service_reads_upload_incrementally(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    result = FileIngestionResult(
        "doc-id", UUID(int=11), ContentStatus.new_content, False, True, False, False
    )
    client = make_client(ingestion_result=result)
    client.app.dependency_overrides[get_file_fingerprint_service] = lambda: FileFingerprintService(
        read_buffer_size=3
    )

    response = post_upload(client, content=b"%PDF-1.7-streamed")

    assert response.status_code == 202
    submitted = client.app.state.file_ingestion_service.submit.call_args.args[0]
    assert submitted.fingerprint.file_size_bytes == len(b"%PDF-1.7-streamed")


def test_upload_requires_ingest_api_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    response = make_client().post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user"},
        files={"file": ("policy.pdf", b"%PDF-1.7", "application/pdf")},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid ingest API key."
