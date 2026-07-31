from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.routes.health import get_health_service
from core.authentication import ApiPrincipal
from main import app
from operations.api.dependencies import get_authenticated_principal
from operations.application.authorization import OperationsPermission
from operations.application.health import HealthService
from operations.domain.health import DependencyHealthResult, HealthErrorCode, HealthStatus


class FixedCheck:
    def __init__(self, name, required, status, code=None):
        self.name = name
        self.required = required
        self.status = status
        self.code = code
        self.calls = 0

    async def check(self):
        self.calls += 1
        return DependencyHealthResult(
            name=self.name,
            status=self.status,
            required=self.required,
            latency_ms=1,
            code=self.code,
            checked_at=datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc),
        )


class RaisingCheck:
    name = "postgres"
    required = True

    async def check(self):
        raise RuntimeError("postgresql://operator:secret@internal/database")


def client_with(*checks):
    app.dependency_overrides[get_health_service] = lambda: HealthService(checks, timeout_seconds=1)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_liveness_is_public_minimal_and_does_not_invoke_dependency_checks():
    check = FixedCheck("postgres", True, HealthStatus.unhealthy)
    response = client_with(check).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert check.calls == 0
    assert "postgres" not in response.text


def test_readiness_is_minimal_and_uses_required_dependency_health_only():
    optional = FixedCheck(
        "redis", False, HealthStatus.unhealthy, HealthErrorCode.dependency_unavailable
    )
    ready_response = client_with(FixedCheck("postgres", True, HealthStatus.healthy), optional).get(
        "/health/ready"
    )
    unavailable_response = client_with(
        FixedCheck("postgres", True, HealthStatus.unhealthy, HealthErrorCode.dependency_unavailable)
    ).get("/health/ready")

    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}
    assert unavailable_response.status_code == 503
    assert unavailable_response.json() == {"status": "not_ready"}
    assert "postgres" not in unavailable_response.text
    assert "dependency_unavailable" not in unavailable_response.text


def test_existing_health_route_remains_available_with_compatible_success_contract():
    response = client_with(FixedCheck("postgres", True, HealthStatus.healthy)).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_authorized_admin_diagnostics_returns_metadata_and_safe_check_results(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    response = client_with(
        FixedCheck("postgres", True, HealthStatus.healthy),
        FixedCheck("redis", False, HealthStatus.unhealthy, HealthErrorCode.dependency_unavailable),
    ).get("/admin/operations/health", headers={"X-API-Key": "admin-secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert [check["name"] for check in response.json()["checks"]] == ["postgres", "redis"]
    assert datetime.fromisoformat(response.json()["generated_at"].replace("Z", "+00:00"))
    assert "admin-secret" not in response.text


def test_admin_diagnostics_converts_raw_check_exception_to_safe_unknown_result(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")

    response = client_with(RaisingCheck()).get(
        "/admin/operations/health", headers={"X-API-Key": "admin-secret"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unhealthy"
    assert response.json()["checks"][0]["status"] == "unknown"
    assert response.json()["checks"][0]["code"] == "dependency_check_failed"
    assert "secret" not in response.text
    assert "internal" not in response.text


def test_admin_diagnostics_requires_read_access(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("INGEST_API_KEY", "ingest-secret")
    client = client_with(FixedCheck("postgres", True, HealthStatus.healthy))

    assert client.get("/admin/operations/health").status_code == 401
    assert (
        client.get("/admin/operations/health", headers={"X-API-Key": "ingest-secret"}).status_code
        == 403
    )


def test_admin_diagnostics_accepts_read_only_principal_without_execute_permission():
    app.dependency_overrides[get_authenticated_principal] = lambda: ApiPrincipal(
        identifier="read-only-operator",
        permissions=frozenset({OperationsPermission.read.value}),
    )

    response = client_with(FixedCheck("postgres", True, HealthStatus.healthy)).get(
        "/admin/operations/health"
    )

    assert response.status_code == 200


def test_health_routes_are_documented_with_public_and_protected_security():
    app.openapi_schema = None
    schema = app.openapi()

    assert schema["paths"]["/health/live"]["get"].get("security", []) == []
    assert schema["paths"]["/health/ready"]["get"].get("security", []) == []
    operation = schema["paths"]["/admin/operations/health"]["get"]
    assert operation["security"] == [{"AdminApiKey": []}]
    assert "401" in operation["responses"]
    assert "403" in operation["responses"]
