from fastapi.testclient import TestClient

from assistant.schemas import HealthResponse


def test_health_routes_preserve_existing_health_and_expose_assistant_health(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    from main import app

    client = TestClient(app)

    response = client.get("/health")
    assistant_response = client.get("/assistant/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert assistant_response.status_code == 200
    assert HealthResponse.model_validate(assistant_response.json()) == HealthResponse(status="ok")

    openapi = app.openapi()
    registered_paths = set(openapi["paths"])
    assert {"/ingest", "/ingest/upload", "/chunks", "/rag-chat", "/audit-logs"}.issubset(
        registered_paths
    )

    health_response_schema = openapi["paths"]["/assistant/health"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert health_response_schema == {"$ref": "#/components/schemas/HealthResponse"}


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
        "SourceReference",
    }.issubset(openapi["components"]["schemas"])
    assert "/assistant/chat" not in openapi["paths"]
