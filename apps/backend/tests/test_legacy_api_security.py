from fastapi.testclient import TestClient

from main import app

LEGACY_ROUTES = (
    ("post", "/assistant/chat"),
    ("post", "/rag-chat"),
    ("get", "/audit-logs"),
    ("get", "/chunks"),
    ("post", "/ingest"),
)


def test_legacy_public_routes_are_not_mounted_or_documented() -> None:
    client = TestClient(app)
    documented_paths = set(app.openapi()["paths"])

    for method, path in LEGACY_ROUTES:
        response = client.request(method, path, json={} if method == "post" else None)
        assert response.status_code == 404
        assert path not in documented_paths


def test_authenticated_upload_integration_remains_mounted() -> None:
    assert "/ingest/upload" in app.openapi()["paths"]
