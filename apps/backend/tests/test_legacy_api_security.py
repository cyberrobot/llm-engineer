import pytest
from fastapi.testclient import TestClient

from main import app
from shared.dependencies.rate_limit import limiter

REMOVED_ROUTES = (
    ("post", "/assistant/chat"),
    ("get", "/chunks"),
    ("post", "/ingest"),
)


@pytest.fixture(autouse=True)
def disable_rate_limits_for_route_contract_tests():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


def test_unused_legacy_public_routes_are_not_mounted_or_documented() -> None:
    client = TestClient(app)
    documented_paths = set(app.openapi()["paths"])

    for method, path in REMOVED_ROUTES:
        response = client.request(method, path, json={} if method == "post" else None)
        assert response.status_code == 404
        assert path not in documented_paths

    assert "/admin/assistants/rag-chat" not in documented_paths
    assert "/admin/operations/audit/rag" not in documented_paths


def test_authenticated_upload_integration_remains_mounted_and_rejects_missing_key(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("INGEST_API_KEY", "expected-ingest-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

    response = TestClient(app).post(
        "/ingest/upload",
        files={"file": ("policy.pdf", b"%PDF-1.7", "application/pdf")},
    )

    assert response.status_code == 401
    assert list(tmp_path.iterdir()) == []
    assert "/ingest/upload" in app.openapi()["paths"]
