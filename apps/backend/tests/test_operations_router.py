from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from main import app
from operations.api.dependencies import require_operations_execute
from operations.api.models import OperationsRootResponse


def test_authorized_admin_can_access_registered_operations_root(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")

    response = TestClient(app).get(
        "/admin/operations",
        headers={"X-API-Key": "admin-secret"},
    )

    assert response.status_code == 200
    parsed = OperationsRootResponse.model_validate(response.json())
    assert parsed.service == "operations"
    assert parsed.status == "available"
    assert parsed.capabilities == ["health"]
    assert parsed.generated_at.tzinfo is not None
    assert parsed.generated_at.utcoffset() is not None
    assert parsed.generated_at.utcoffset().total_seconds() == 0
    assert datetime.fromisoformat(response.json()["generated_at"].replace("Z", "+00:00"))
    assert set(response.json()) == {"service", "status", "capabilities", "generated_at"}
    assert "admin-secret" not in response.text


def test_missing_or_invalid_admin_authentication_uses_typed_safe_401(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    client = TestClient(app)

    for headers in ({}, {"X-API-Key": "wrong"}, {"Authorization": "Bearer unsupported"}):
        response = client.get("/admin/operations", headers=headers)

        assert response.status_code == 401
        assert response.json() == {
            "detail": {
                "code": "admin_authentication_required",
                "message": "Administrative authentication is required.",
            }
        }
        assert response.headers["www-authenticate"] == "ApiKey"
        assert "admin-secret" not in response.text


def test_authenticated_ingestion_principal_is_forbidden_from_operations(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("INGEST_API_KEY", "ingest-secret")

    response = TestClient(app).get(
        "/admin/operations",
        headers={"X-API-Key": "ingest-secret"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "admin_permission_denied",
            "message": "The authenticated principal lacks the required administrative permission.",
        }
    }
    assert "ingest-secret" not in response.text


def test_execute_dependency_requires_execute_permission(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("INGEST_API_KEY", "ingest-secret")
    test_app = FastAPI()

    @test_app.post("/execute", dependencies=[Depends(require_operations_execute)])
    def execute():
        return {"accepted": True}

    client = TestClient(test_app)

    assert client.post("/execute", headers={"X-API-Key": "admin-secret"}).status_code == 200
    assert client.post("/execute", headers={"X-API-Key": "ingest-secret"}).status_code == 403


def test_operations_openapi_is_tagged_documented_and_secure_by_default():
    app.openapi_schema = None
    openapi = app.openapi()
    operation = openapi["paths"]["/admin/operations"]["get"]

    assert operation["tags"] == ["Operations Administration"]
    assert operation["security"] == [{"AdminApiKey": []}]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/OperationsRootResponse"
    }
    assert "401" in operation["responses"]
    assert "403" in operation["responses"]
    operations_paths = {
        path: methods
        for path, methods in openapi["paths"].items()
        if path.startswith("/admin/operations")
    }
    assert set(operations_paths) == {"/admin/operations", "/admin/operations/health"}
    assert all(
        details.get("security") == [{"AdminApiKey": []}]
        for methods in operations_paths.values()
        for details in methods.values()
    )


def test_unconfigured_admin_key_fails_closed(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("INGEST_API_KEY", raising=False)

    response = TestClient(app).get("/admin/operations", headers={"X-API-Key": "anything"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "admin_authentication_required"
