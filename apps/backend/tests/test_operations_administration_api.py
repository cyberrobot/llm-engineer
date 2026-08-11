from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app
from operations.api.administration_dependencies import (
    get_audit_query_service,
    get_cache_administration_service,
    get_job_operations_service,
    get_maintenance_service,
    get_operations_summary_service,
    get_runtime_state_store,
)
from operations.api.health_dependencies import get_health_service
from operations.application.administration import (
    AuditQueryService,
    CacheAdministrationService,
    JobOperationsService,
    MaintenanceService,
    OperationsSummaryService,
)
from operations.application.health import HealthService
from operations.domain.administration import (
    AuditFilters,
    AuditResult,
    JobCounts,
    OperationalJob,
    OperationsDependencyUnavailable,
)
from operations.infrastructure.memory import (
    InMemoryAuditStore,
    InMemoryCacheRegion,
    InMemoryJobStore,
    InMemoryRuntimeStateStore,
)

NOW = datetime(2026, 8, 11, 10, tzinfo=timezone.utc)


def _client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("INGEST_API_KEY", "ingest-secret")
    runtime = InMemoryRuntimeStateStore()
    audit = AuditQueryService(InMemoryAuditStore(), now=lambda: NOW)
    jobs = InMemoryJobStore(
        [
            OperationalJob(
                id=uuid4(),
                status="failed",
                created_at=NOW,
                started_at=NOW,
                completed_at=NOW,
                retry_count=2,
                last_error="Safe failure summary.",
            )
        ]
    )
    app.dependency_overrides[get_cache_administration_service] = lambda: CacheAdministrationService(
        {"assistant": InMemoryCacheRegion("assistant", {"assistant:123": "value"})}
    )
    app.dependency_overrides[get_audit_query_service] = lambda: audit
    app.dependency_overrides[get_maintenance_service] = lambda: MaintenanceService(
        runtime, now=lambda: NOW
    )
    app.dependency_overrides[get_job_operations_service] = lambda: JobOperationsService(jobs)
    app.dependency_overrides[get_health_service] = lambda: HealthService(
        [], timeout_seconds=1, now=lambda: NOW
    )
    return TestClient(app), audit


def _cleanup():
    app.dependency_overrides.clear()


def test_administration_endpoints_are_secure_mutations_are_audited_and_reads_are_safe(monkeypatch):
    client, audit = _client(monkeypatch)
    headers = {"X-API-Key": "admin-secret", "X-Request-ID": str(uuid4())}
    try:
        assert client.get("/admin/operations/cache").status_code == 401
        assert (
            client.get(
                "/admin/operations/cache", headers={"X-API-Key": "ingest-secret"}
            ).status_code
            == 403
        )
        assert (
            client.get("/admin/operations/cache", headers=headers).json()["items"][0]["name"]
            == "assistant"
        )

        cleared = client.post(
            "/admin/operations/cache/key",
            headers=headers,
            json={"region": "assistant", "key": "assistant:123"},
        )
        assert cleared.status_code == 200
        assert cleared.json()["success"] is True
        assert cleared.json()["correlation_id"] == headers["X-Request-ID"]

        cleared_region = client.post(
            "/admin/operations/cache/regions/assistant/clear", headers=headers
        )
        cleared_all = client.post("/admin/operations/cache/clear", headers=headers)
        assert cleared_region.status_code == 200
        assert cleared_all.status_code == 200

        maintenance = client.put(
            "/admin/operations/maintenance",
            headers=headers,
            json={"enabled": True},
        )
        assert maintenance.status_code == 200
        assert maintenance.json()["enabled"] is True
        assert client.get("/admin/operations", headers=headers).status_code == 200
        assert client.get("/health/live").status_code == 200

        jobs = client.get("/admin/operations/jobs", headers=headers)
        assert jobs.status_code == 200
        assert jobs.json()["items"][0]["last_error"] == "Safe failure summary."
        job_id = jobs.json()["items"][0]["id"]
        assert client.get(f"/admin/operations/jobs/{job_id}", headers=headers).status_code == 200

        audit_page = client.get(
            "/admin/operations/audit", headers=headers, params={"action": "maintenance.update"}
        )
        assert audit_page.status_code == 200
        assert audit_page.json()["total"] == 1
        detail_id = audit_page.json()["items"][0]["id"]
        detail = client.get(f"/admin/operations/audit/{detail_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["request_id"] == headers["X-Request-ID"]
        assert "message" not in detail.text
        assert audit.count_since(NOW.replace(hour=0)) == 4

        summary = client.get("/admin/operations/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json() == {
            "health": "healthy",
            "maintenance": True,
            "cache": {"regions": 1},
            "jobs": {"running": 0, "failed": 1},
            "audit": {"today": 4},
        }
    finally:
        _cleanup()


@pytest.mark.parametrize("path", ["/admin/operations/audit", "/admin/operations/jobs"])
def test_audit_and_job_visibility_use_shared_administrator_authorization(monkeypatch, path):
    client, _ = _client(monkeypatch)
    try:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key": "ingest-secret"}).status_code == 403
        assert client.get(path, headers={"X-API-Key": "admin-secret"}).status_code == 200
    finally:
        _cleanup()


def test_cache_inspection_excludes_payloads_and_repeated_clears_are_safe(monkeypatch):
    client, audit = _client(monkeypatch)
    headers = {"X-API-Key": "admin-secret"}
    try:
        inspected = client.get("/admin/operations/cache", headers=headers)

        assert inspected.status_code == 200
        assert inspected.json()["items"][0]["entries"] == 1
        assert "assistant:123" not in inspected.text
        assert "value" not in inspected.text

        region_results = [
            client.post("/admin/operations/cache/regions/assistant/clear", headers=headers)
            for _ in range(2)
        ]
        all_results = [
            client.post("/admin/operations/cache/clear", headers=headers) for _ in range(2)
        ]

        assert [response.status_code for response in region_results] == [200, 200]
        assert [response.status_code for response in all_results] == [200, 200]
        assert audit.list(AuditFilters(), limit=10, offset=0).total == 4
    finally:
        _cleanup()


def test_unknown_operational_resources_return_typed_safe_errors(monkeypatch):
    client, audit = _client(monkeypatch)
    request_id = str(uuid4())
    headers = {"X-API-Key": "admin-secret", "X-Request-ID": request_id}
    try:
        missing_region = client.post(
            "/admin/operations/cache/regions/missing/clear", headers=headers
        )
        missing_key = client.post(
            "/admin/operations/cache/key",
            headers=headers,
            json={"region": "assistant", "key": "missing-key"},
        )
        missing_audit = client.get(f"/admin/operations/audit/{uuid4()}", headers=headers)
        missing_job = client.get(f"/admin/operations/jobs/{uuid4()}", headers=headers)

        assert missing_region.status_code == 404
        assert missing_region.json()["detail"]["code"] == "cache_region_not_found"
        assert missing_key.status_code == 404
        assert missing_key.json()["detail"]["code"] == "cache_key_not_found"
        assert missing_audit.status_code == 404
        assert missing_audit.json()["detail"]["code"] == "audit_entry_not_found"
        assert missing_job.status_code == 404
        assert missing_job.json()["detail"]["code"] == "operational_job_not_found"
        invalid = client.put(
            "/admin/operations/maintenance",
            headers=headers,
            json={"enabled": True, "message": "x" * 501},
        )
        assert invalid.status_code == 400
        assert invalid.json()["detail"]["code"] == "invalid_admin_request"
        failures = audit.list(filters=AuditFilters(result=AuditResult.failure), limit=10, offset=0)
        assert failures.total == 2
        assert {entry.action for entry in failures.items} == {
            "cache.region.clear",
            "cache.key.invalidate",
        }
        assert all(entry.actor == "admin-api-key" for entry in failures.items)
        assert all(entry.request_id == request_id for entry in failures.items)
        assert "missing-key" not in repr(failures.items)
    finally:
        _cleanup()


def test_summary_dependency_failure_uses_safe_standard_error(monkeypatch):
    client, _ = _client(monkeypatch)

    def unavailable():
        raise OperationsDependencyUnavailable("private database address")

    app.dependency_overrides[get_operations_summary_service] = lambda: OperationsSummaryService(
        health=unavailable,
        maintenance=unavailable,
        cache=lambda: 0,
        jobs=lambda: JobCounts(running=0, failed=0),
        audit=lambda: 0,
    )
    try:
        response = client.get("/admin/operations/summary", headers={"X-API-Key": "admin-secret"})

        assert response.status_code == 503
        assert response.json() == {
            "detail": {
                "code": "dependency_unavailable",
                "message": "A required dependency is unavailable.",
            }
        }
        assert "private database address" not in response.text
    finally:
        _cleanup()


def test_maintenance_centrally_blocks_public_assistant_traffic_but_not_admin_or_probes(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    service = MaintenanceService(get_runtime_state_store(), now=lambda: NOW)
    service.update(enabled=False, message=None, actor="operator")
    client = TestClient(app)
    try:
        allowed = client.post(
            "/public/assistants/demo/chat",
            headers={"Origin": "http://localhost:5173"},
            json={"message": "hello"},
        )
        assert "maintenance_mode" not in allowed.text

        service.update(enabled=True, message=None, actor="operator")
        request_id = str(uuid4())
        blocked = client.post(
            "/public/assistants/demo/chat",
            headers={"Origin": "http://localhost:5173", "X-Request-ID": request_id},
            json={"message": "hello"},
        )

        assert blocked.status_code == 503
        assert blocked.json() == {
            "detail": {
                "code": "maintenance_mode",
                "message": "The service is undergoing maintenance.",
            }
        }
        assert blocked.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert blocked.headers["x-request-id"] == request_id
        for path in ("/assistant/chat", "/rag-chat"):
            legacy_request_id = str(uuid4())
            legacy_blocked = client.post(
                path,
                headers={
                    "Origin": "http://localhost:5173",
                    "X-Request-ID": legacy_request_id,
                },
                json={},
            )
            assert legacy_blocked.status_code == 503
            assert legacy_blocked.json()["detail"] == {
                "code": "maintenance_mode",
                "message": "The service is undergoing maintenance.",
            }
            assert legacy_blocked.headers["access-control-allow-origin"] == (
                "http://localhost:5173"
            )
            assert legacy_blocked.headers["x-request-id"] == legacy_request_id
        assert (
            client.get("/admin/operations", headers={"X-API-Key": "admin-secret"}).status_code
            == 200
        )
        admin_auth = client.get("/admin/auth/me")
        assert admin_auth.status_code == 401
        assert "maintenance_mode" not in admin_auth.text
        assistant_health = client.get("/assistant/health")
        assert "maintenance_mode" not in assistant_health.text
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health").status_code == 503
    finally:
        service.update(enabled=False, message=None, actor="operator")
