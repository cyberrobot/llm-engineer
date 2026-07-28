from fastapi.testclient import TestClient


def test_health_routes_preserve_existing_health_and_expose_assistant_health(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    from main import app

    client = TestClient(app)

    response = client.get("/health")
    assistant_response = client.get("/assistant/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert assistant_response.status_code == 200
    assert assistant_response.json() == {"status": "ok"}

    registered_paths = set(app.openapi()["paths"])
    assert {"/ingest", "/ingest/upload", "/chunks", "/rag-chat", "/audit-logs"}.issubset(
        registered_paths
    )
