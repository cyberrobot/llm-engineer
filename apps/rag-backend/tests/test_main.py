import sys
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
import application
import main
from main import app, rate_windows
from security import Authorization


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


def test_readiness_rejects_missing_runtime_configuration():
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


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


def test_rag_rate_limit_matches_the_frozen_error_contract():
    rate_windows.clear()
    with TestClient(app) as client:
        for _ in range(20):
            assert (
                client.post("/rag-chat", json={"message": "hello"}).status_code == 401
            )
        response = client.post("/rag-chat", json={"message": "hello"})

    assert response.status_code == 429
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please wait a moment before trying again.",
            "retry_after_seconds": 60,
        }
    }


def test_early_request_body_failure_has_a_normalized_request_id_and_no_store():
    with TestClient(app) as client:
        response = client.post(
            "/rag-chat",
            content=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "invalid"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request body size."}
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.headers["X-Request-ID"]) == 36


def test_timeout_cannot_be_followed_by_audit_or_cache_mutations(monkeypatch):
    rate_windows.clear()

    class RecordingCache:
        writes = 0

        def get(self, *_args):
            return None

        def set(self, *_args):
            self.writes += 1

        def ping(self):
            return True

        def close(self):
            pass

    class RecordingAudit:
        writes = 0

        def write(self, **_kwargs):
            self.writes += 1

        def latest(self, **_kwargs):
            return None

    class Provider:
        def close(self):
            pass

    cache = RecordingCache()
    audit = RecordingAudit()

    def delayed_outcome(*_args, **_kwargs):
        time.sleep(0.05)
        return application.RagChatOutcome(
            response={"reply": {"answer": "late", "source_ids": []}, "sources": []},
            audit_event={"role": "doctor"},
            cache_response={"reply": {"answer": "late", "source_ids": []}},
        )

    monkeypatch.setattr(main, "Cache", lambda: cache)
    monkeypatch.setattr(main, "AuditRepository", lambda: audit)
    monkeypatch.setattr(main, "Provider", Provider)
    monkeypatch.setattr(main, "prepare_rag_chat", delayed_outcome)
    monkeypatch.setattr(
        main,
        "require_admin",
        lambda _request: Authorization(principal_id="administrator"),
    )
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, request_timeout_seconds=0.01),
    )

    with TestClient(app) as client:
        response = client.post("/rag-chat", json={"message": "hello"})
        time.sleep(0.1)

    assert response.status_code == 504
    assert response.headers["Cache-Control"] == "no-store"
    assert audit.writes == 0
    assert cache.writes == 0
