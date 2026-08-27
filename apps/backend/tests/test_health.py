from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from assistant.schemas import HealthResponse


def test_health_routes_preserve_existing_health_and_expose_assistant_health(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DISABLE_CACHE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    from main import app

    client = TestClient(app)

    response = client.get("/health")
    assistant_response = client.get("/assistant/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert assistant_response.status_code == 200
    assert HealthResponse.model_validate(assistant_response.json()) == HealthResponse(status="ok")

    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").json() == {"status": "ready"}

    openapi = app.openapi()
    registered_paths = set(openapi["paths"])
    assert {
        "/assistant/knowledge/ingestions",
        "/assistant/knowledge/ingestions/{jobId}",
        "/assistant/knowledge/status",
        "/ingest/upload",
        "/admin/assistants/rag-chat",
        "/admin/operations/audit/rag",
    }.issubset(registered_paths)

    health_response_schema = openapi["paths"]["/assistant/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert health_response_schema == {"$ref": "#/components/schemas/HealthResponse"}


def test_liveness_stays_healthy_when_readiness_dependency_fails():
    from api.routes.health import get_health_service
    from main import app
    from operations.application.health import HealthService
    from operations.domain.health import DependencyHealthResult, HealthErrorCode, HealthStatus

    class UnavailableCheck:
        name = "postgres"
        required = True

        async def check(self):
            return DependencyHealthResult(
                name=self.name,
                status=HealthStatus.unhealthy,
                required=self.required,
                latency_ms=1,
                code=HealthErrorCode.dependency_unavailable,
                checked_at=datetime.now(timezone.utc),
            )

    app.dependency_overrides[get_health_service] = lambda: HealthService(
        [UnavailableCheck()], timeout_seconds=1
    )
    client = TestClient(app)

    try:
        assert client.get("/health/live").status_code == 200
        readiness = client.get("/health/ready")
        assert readiness.status_code == 503
        assert readiness.json() == {"status": "not_ready"}
        assert "postgres" not in readiness.text
    finally:
        app.dependency_overrides.pop(get_health_service, None)


def test_metrics_endpoint_exports_prometheus_without_sensitive_identifiers(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    from main import app

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "ingestion_jobs_created_total" in response.text
    assert "document_id=" not in response.text
    assert "worker_id=" not in response.text


def test_requests_receive_a_stable_valid_correlation_identifier(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    from main import app

    supplied = "2aab3ef7-d57f-4f6f-8dda-25916ae2ce8c"
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": supplied})
    generated = TestClient(app).get("/health/live", headers={"X-Request-ID": "not-a-uuid"})

    assert response.headers["X-Request-ID"] == supplied
    UUID(generated.headers["X-Request-ID"])


def test_openapi_includes_versioned_assistant_contracts(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    from main import app

    openapi = app.openapi()

    assert openapi["info"]["version"] == "1.0.0"
    assert {
        "ChatRequest",
        "ChatResponse",
        "ErrorResponse",
        "HealthResponse",
        "IngestionJobResponse",
        "KnowledgeStatusResponse",
        "SourceReference",
        "StartIngestionRequest",
    }.issubset(openapi["components"]["schemas"])
    assert "/public/assistants/{assistant_slug}/chat" in openapi["paths"]
