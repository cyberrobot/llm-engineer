import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
from main import app


def test_service_exposes_only_rag_routes():
    with TestClient(app) as client:
        assert sorted(client.get("/openapi.json").json()["paths"]) == [
            "/audit-logs",
            "/health/live",
            "/health/ready",
            "/rag-chat",
        ]


def test_liveness_does_not_require_authentication():
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rag_routes_reject_anonymous_callers():
    with TestClient(app) as client:
        chat = client.post("/rag-chat", json={"message": "hello"})
        logs = client.get("/audit-logs")
    assert chat.status_code == 401
    assert logs.status_code == 401


def test_request_id_is_normalized_and_returned():
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "not-a-uuid"})
    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 36
