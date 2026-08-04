from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_admin import router
from assistant.api.dependencies import get_assistant_administration_service
from assistant.application.assistant_admin_service import AssistantAdministrationService
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from core.exceptions import register_exception_handlers

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
FIRST_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_ID = UUID("22222222-2222-4222-8222-222222222222")


def _client(*, authenticated: bool = True, trusted: bool = True) -> TestClient:
    identifiers = iter((FIRST_ID, SECOND_ID))
    service = AssistantAdministrationService(
        InMemoryAssistantRepository(()), clock=lambda: NOW, id_factory=lambda: next(identifiers)
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_assistant_administration_service] = lambda: service
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    if trusted:
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/admin/assistants", None),
        ("get", f"/admin/assistants/{FIRST_ID}", None),
        ("post", "/admin/assistants", {"slug": "one", "name": "One"}),
        (
            "patch",
            f"/admin/assistants/{FIRST_ID}",
            {"concurrency_token": NOW.isoformat(), "name": "One"},
        ),
        ("delete", f"/admin/assistants/{FIRST_ID}", None),
    ],
)
def test_every_route_requires_an_administrator(method: str, path: str, json: object) -> None:
    response = _client(authenticated=False).request(method, path, json=json)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/admin/assistants", {"slug": "one", "name": "One"}),
        (
            "patch",
            f"/admin/assistants/{FIRST_ID}",
            {"concurrency_token": NOW.isoformat(), "name": "One"},
        ),
        ("delete", f"/admin/assistants/{FIRST_ID}", None),
    ],
)
def test_every_write_route_requires_a_trusted_origin(method: str, path: str, json: object) -> None:
    response = _client(trusted=False).request(method, path, json=json)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"


def test_create_list_detail_update_and_delete_contract() -> None:
    client = _client()
    created = client.post("/admin/assistants", json={"slug": "legal-review", "name": "  Юрист ✓  "})
    assert created.status_code == 201
    assert created.headers["location"] == f"/admin/assistants/{FIRST_ID}"
    assert created.json()["name"] == "Юрист ✓"
    assert created.json()["status"] == "inactive"
    assert created.json()["visibility"] == "private"

    detail = client.get(f"/admin/assistants/{FIRST_ID}")
    assert detail.status_code == 200
    assert detail.json()["knowledge_source_count"] == 0
    assert detail.json()["deletion_allowed"] is True
    token = detail.json()["concurrency_token"]

    updated = client.patch(
        f"/admin/assistants/{FIRST_ID}",
        json={"concurrency_token": token, "status": "active", "visibility": "public"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"
    assert updated.json()["visibility"] == "public"
    assert updated.json()["concurrency_token"] != token

    stale = client.patch(
        f"/admin/assistants/{FIRST_ID}",
        json={"concurrency_token": token, "name": "Stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "assistant_update_conflict"

    listing = client.get("/admin/assistants?status=active&visibility=public")
    assert listing.status_code == 200
    assert listing.json() == {
        "items": [updated.json()],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }

    deleted = client.delete(f"/admin/assistants/{FIRST_ID}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/admin/assistants/{FIRST_ID}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"slug": "Invalid", "name": "Name"},
        {"slug": "valid", "name": " "},
        {"slug": "valid", "name": "control\u0001"},
        {"slug": "valid", "name": "Name", "unknown": True},
    ],
)
def test_invalid_create_requests_use_safe_structured_validation(payload: dict[str, object]) -> None:
    response = _client().post("/admin/assistants", json=payload)
    assert response.status_code in {400, 422}
    assert response.json()["detail"]["code"] == "invalid_request"


def test_pagination_bounds_immutable_fields_empty_patch_and_invalid_uuid() -> None:
    client = _client()
    for path in ("/admin/assistants?limit=101", "/admin/assistants?offset=-1"):
        response = client.get(path)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"
    assert client.get("/admin/assistants/not-a-uuid").status_code == 422

    client.post("/admin/assistants", json={"slug": "one", "name": "One"})
    token = NOW.isoformat()
    for payload in (
        {"concurrency_token": token},
        {"concurrency_token": token, "slug": "new"},
        {"concurrency_token": token, "id": str(SECOND_ID)},
    ):
        response = client.patch(f"/admin/assistants/{FIRST_ID}", json=payload)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"


def test_duplicate_slug_and_missing_assistant_have_stable_safe_errors() -> None:
    client = _client()
    payload = {"slug": "one", "name": "One"}
    assert client.post("/admin/assistants", json=payload).status_code == 201
    duplicate = client.post("/admin/assistants", json=payload)
    missing = client.get(f"/admin/assistants/{SECOND_ID}")
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "assistant_slug_conflict",
        "message": "Assistant slug already exists.",
    }
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "assistant_not_found"


def test_openapi_documents_routes_security_models_conflicts_and_validation() -> None:
    schema = _client().get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/admin/assistants"]) >= {"get", "post"}
    assert set(paths["/admin/assistants/{assistant_id}"]) >= {"get", "patch", "delete"}
    for path, method in (
        ("/admin/assistants", "post"),
        ("/admin/assistants/{assistant_id}", "patch"),
        ("/admin/assistants/{assistant_id}", "delete"),
    ):
        operation = paths[path][method]
        assert "409" in operation["responses"]
        assert "422" in operation["responses"]
        assert operation["security"]
    assert "immutable" in paths["/admin/assistants"]["post"]["description"]
    assert "concurrency token" in paths["/admin/assistants/{assistant_id}"]["patch"]["description"]
