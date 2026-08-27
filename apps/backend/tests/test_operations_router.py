from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import get_administrator_auth_service
from admin_auth.domain import AdministratorStatus
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import InMemoryAdministratorAuthRepository
from admin_auth.service import AdministratorAuthenticationService
from main import app
from operations.api.dependencies import require_operations_execute
from operations.api.models import OperationsRootResponse

PASSWORD = "correct horse battery staple"


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 12, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def browser_operations(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("INGEST_API_KEY", "ingest-secret")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_NAME", "redmoor_admin_session")
    repository = InMemoryAdministratorAuthRepository()
    clock = MutableClock()
    service = AdministratorAuthenticationService(
        repository,
        AdministratorPasswordService(),
        session_ttl_seconds=3600,
        login_max_failures=3,
        login_lockout_seconds=300,
        clock=clock,
        token_factory=lambda: "valid-browser-session",
    )
    service.bootstrap("admin@example.com", PASSWORD)
    login = service.login("admin@example.com", PASSWORD)
    app.dependency_overrides[get_administrator_auth_service] = lambda: service
    try:
        yield TestClient(app), service, repository, clock, login
    finally:
        app.dependency_overrides.pop(get_administrator_auth_service, None)


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
    assert parsed.capabilities == [
        "health",
        "cache",
        "audit",
        "maintenance",
        "jobs",
        "summary",
    ]
    assert parsed.generated_at.tzinfo is not None
    assert parsed.generated_at.utcoffset() is not None
    assert parsed.generated_at.utcoffset().total_seconds() == 0
    assert datetime.fromisoformat(response.json()["generated_at"].replace("Z", "+00:00"))
    assert set(response.json()) == {"service", "status", "capabilities", "generated_at"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
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


@pytest.mark.parametrize(
    ("api_key", "session_token", "expected_status"),
    [
        (None, None, 401),
        ("admin-secret", None, 200),
        (None, "valid-browser-session", 200),
        ("admin-secret", "valid-browser-session", 200),
        ("wrong", "valid-browser-session", 401),
        ("admin-secret", "invalid-session", 200),
        ("wrong", "invalid-session", 401),
        ("ingest-secret", "valid-browser-session", 403),
    ],
)
def test_operations_credentials_have_explicit_api_key_precedence(
    browser_operations, api_key, session_token, expected_status
):
    client, _service, _repository, _clock, _login = browser_operations
    headers = {"X-API-Key": api_key} if api_key is not None else {}
    if session_token is not None:
        client.cookies.set("redmoor_admin_session", session_token)

    response = client.get("/admin/operations", headers=headers)

    assert response.status_code == expected_status
    if expected_status == 401:
        assert response.json()["detail"]["code"] == "admin_authentication_required"
    elif expected_status == 403:
        assert response.json()["detail"]["code"] == "admin_permission_denied"


@pytest.mark.parametrize("session_state", ["expired", "revoked", "disabled"])
def test_inactive_administrator_sessions_cannot_access_operations(
    browser_operations, session_state
):
    client, service, repository, clock, login = browser_operations
    client.cookies.set("redmoor_admin_session", login.session_token)
    if session_state == "expired":
        clock.now += timedelta(hours=1)
    elif session_state == "revoked":
        service.logout(login.session_token)
    else:
        repository.set_administrator_status(login.administrator.id, AdministratorStatus.disabled)

    response = client.get("/admin/operations")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "admin_authentication_required"


def test_browser_operations_requests_use_existing_credentialed_cors_policy(browser_operations):
    client, _service, _repository, _clock, login = browser_operations
    client.cookies.set("redmoor_admin_session", login.session_token)

    response = client.get(
        "/admin/operations",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


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
    assert operation["security"] == [
        {"AdminApiKey": []},
        {"AdministratorSessionCookie": []},
    ]
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
    assert set(operations_paths) == {
        "/admin/operations",
        "/admin/operations/health",
        "/admin/operations/cache",
        "/admin/operations/cache/clear",
        "/admin/operations/cache/regions/{region}/clear",
        "/admin/operations/cache/key",
        "/admin/operations/maintenance",
        "/admin/operations/audit",
        "/admin/operations/audit/rag",
        "/admin/operations/audit/{entry_id}",
        "/admin/operations/jobs",
        "/admin/operations/jobs/{job_id}",
        "/admin/operations/summary",
    }
    assert all(
        details.get("security") == [{"AdminApiKey": []}, {"AdministratorSessionCookie": []}]
        for methods in operations_paths.values()
        for details in methods.values()
    )


def test_unconfigured_admin_key_fails_closed(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("INGEST_API_KEY", raising=False)

    response = TestClient(app).get("/admin/operations", headers={"X-API-Key": "anything"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "admin_authentication_required"
