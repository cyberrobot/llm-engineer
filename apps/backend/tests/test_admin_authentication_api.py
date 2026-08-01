from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import (
    get_administrator_auth_repository,
    get_administrator_auth_service,
    get_login_throttle,
    require_administrator_role,
    require_trusted_admin_origin,
)
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import InMemoryAdministratorAuthRepository
from admin_auth.routes import router
from admin_auth.service import AdministratorAuthenticationService
from admin_auth.throttling import LoginThrottleDecision
from core.exceptions import register_exception_handlers

PASSWORD = "correct horse battery staple"
ORIGIN = "http://localhost:5173"


class AllowingThrottle:
    def check(self, source_ip: str, normalized_email: str) -> LoginThrottleDecision:
        return LoginThrottleDecision(True)


class RejectingThrottle:
    def check(self, source_ip: str, normalized_email: str) -> LoginThrottleDecision:
        return LoginThrottleDecision(False, 17)


@pytest.fixture
def auth_api(monkeypatch) -> Iterator[tuple[TestClient, InMemoryAdministratorAuthRepository]]:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ADMIN_SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("ADMIN_TRUSTED_ORIGINS", ORIGIN)
    repository = InMemoryAdministratorAuthRepository()
    passwords = AdministratorPasswordService()
    service = AdministratorAuthenticationService(
        repository,
        passwords,
        session_ttl_seconds=3600,
        login_max_failures=3,
        login_lockout_seconds=300,
        clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
        token_factory=lambda: "opaque-browser-session-token",
    )
    service.bootstrap("admin@example.com", PASSWORD)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_administrator_auth_repository] = lambda: repository
    app.dependency_overrides[get_administrator_auth_service] = lambda: service
    app.dependency_overrides[get_login_throttle] = AllowingThrottle

    @app.get("/protected", dependencies=[Depends(require_administrator_role)])
    def protected() -> dict[str, bool]:
        return {"allowed": True}

    yield TestClient(app), repository


def test_complete_bootstrap_login_restore_protected_logout_flow(auth_api):
    client, repository = auth_api

    login = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": " ADMIN@EXAMPLE.COM ", "password": PASSWORD},
    )

    assert login.status_code == 200
    assert login.json()["user"]["email"] == "admin@example.com"
    assert set(login.json()["user"]) == {"id", "email", "role"}
    assert "opaque-browser-session-token" not in login.text
    assert login.headers["cache-control"] == "no-store"
    cookie = login.headers["set-cookie"]
    assert "redmoor_admin_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=3600" in cookie
    assert "Secure" not in cookie
    assert repository.sessions[0].token_hash != "opaque-browser-session-token"

    current = client.get("/admin/auth/me")
    assert current.status_code == 200
    assert current.json() == login.json()
    assert client.get("/protected").json() == {"allowed": True}

    logout = client.post("/admin/auth/logout", headers={"Origin": ORIGIN})
    assert logout.status_code == 204
    cleared = logout.headers["set-cookie"]
    assert 'redmoor_admin_session="";' in cleared
    assert "Max-Age=0" in cleared
    assert "HttpOnly" in cleared and "SameSite=lax" in cleared and "Path=/" in cleared
    assert client.get("/admin/auth/me").status_code == 401
    assert client.post("/admin/auth/logout", headers={"Origin": ORIGIN}).status_code == 204


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "invalid", "password": PASSWORD},
        {"email": "admin@example.com"},
        {"email": "admin@example.com", "password": "x" * 1025},
        {"email": "admin@example.com", "password": PASSWORD, "extra": True},
    ],
)
def test_login_validation_has_stable_400_error_contract(auth_api, payload):
    client, _repository = auth_api
    response = client.post("/admin/auth/login", headers={"Origin": ORIGIN}, json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_request"
    assert response.headers["cache-control"] == "no-store"


def test_malformed_json_has_stable_400_error_contract(auth_api):
    client, _repository = auth_api
    response = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        content="{not-json",
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_request"


def test_throttled_login_returns_stable_429_and_retry_after(auth_api):
    client, repository = auth_api
    client.app.dependency_overrides[get_login_throttle] = RejectingThrottle
    response = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "too_many_login_attempts"
    assert response.headers["retry-after"] == "17"
    assert repository.sessions == ()


def test_login_failures_are_generic_and_do_not_create_sessions(auth_api):
    client, repository = auth_api
    wrong = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    unknown = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["detail"]["code"] == "invalid_credentials"
    assert repository.sessions == ()


def test_cookie_authentication_rejects_missing_and_invalid_sessions(auth_api):
    client, _repository = auth_api
    missing = client.get("/admin/auth/me")
    client.cookies.set("redmoor_admin_session", "invalid-token")
    invalid = client.get("/admin/auth/me")
    assert missing.status_code == invalid.status_code == 401
    assert missing.json()["detail"]["code"] == "authentication_required"
    assert invalid.json() == missing.json()


def test_strict_origin_dependency_protects_login_logout_and_future_mutations(auth_api):
    client, _repository = auth_api
    payload = {"email": "admin@example.com", "password": PASSWORD}
    assert client.post("/admin/auth/login", json=payload).status_code == 403
    assert (
        client.post(
            "/admin/auth/login", headers={"Origin": "https://evil.example"}, json=payload
        ).status_code
        == 403
    )
    assert client.post("/admin/auth/logout").status_code == 403

    app = FastAPI()

    @app.post("/future-mutation", dependencies=[Depends(require_trusted_admin_origin)])
    def future_mutation() -> dict[str, bool]:
        return {"ok": True}

    future = TestClient(app)
    assert future.post("/future-mutation", headers={"Origin": ORIGIN}).status_code == 200
    assert future.post("/future-mutation").status_code == 403


def test_production_login_cookie_is_secure(auth_api, monkeypatch):
    client, _repository = auth_api
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_SESSION_COOKIE_SECURE", "true")
    response = client.post(
        "/admin/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": "admin@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_openapi_describes_request_response_and_cookie_security(auth_api):
    client, _repository = auth_api
    schema = client.get("/openapi.json").json()
    assert "/admin/auth/login" in schema["paths"]
    assert "/admin/auth/me" in schema["paths"]
    assert schema["components"]["securitySchemes"]["AdministratorSessionCookie"] == {
        "type": "apiKey",
        "description": "Opaque HTTP-only administrator session cookie.",
        "in": "cookie",
        "name": "redmoor_admin_session",
    }
