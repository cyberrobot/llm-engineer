from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assistant.api.ingest import router
from shared.dependencies.rate_limit import limiter

client_counter = 0


@pytest.fixture(autouse=True)
def disable_rate_limit_for_upload_tests():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def make_client():
    global client_counter
    client_counter += 1
    app = FastAPI()
    app.include_router(router)
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

    with (
        patch("assistant.api.ingest.uuid.uuid4", side_effect=["doc-id", "job-id"]),
        patch("assistant.api.ingest.record_uploaded_document") as record_uploaded_document,
    ):
        response = post_upload(make_client())

    assert response.status_code == 200
    assert response.json() == {
        "document_id": "doc-id",
        "job_id": "job-id",
        "filename": "policy.pdf",
        "status": "uploaded",
        "next_stage": "validate",
    }
    assert (tmp_path / "doc-id.pdf").read_bytes() == b"%PDF-1.7"
    record_uploaded_document.assert_called_once_with(
        "doc-id",
        "job-id",
        "policy",
        ["user", "admin"],
        str(tmp_path / "doc-id.pdf"),
        "policy.pdf",
    )


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

    with (
        patch("assistant.api.ingest.uuid.uuid4", side_effect=["doc-id", "job-id"]),
        patch("assistant.api.ingest.record_uploaded_document") as record_uploaded_document,
    ):
        response = post_upload(make_client())

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file exceeds maximum size."
    assert not (tmp_path / "doc-id.pdf").exists()
    record_uploaded_document.assert_not_called()


def test_upload_requires_ingest_api_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "test-key")

    response = make_client().post(
        "/ingest/upload",
        data={"doc_type": "policy", "access_roles": "user"},
        files={"file": ("policy.pdf", b"%PDF-1.7", "application/pdf")},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid ingest API key."
