from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from admin_auth.api_errors import admin_auth_error
from admin_auth.api_models import AdminAuthErrorCode
from admin_auth.dependencies import get_administrator_auth_service, require_administrator_role
from admin_auth.domain import Administrator
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import InMemoryAdministratorAuthRepository
from admin_auth.service import AdministratorAuthenticationService
from assistant.api.rag import MAX_RAG_MESSAGE_CHARACTERS
from assistant.api.rag_ui_security import RAG_UI_REQUEST_MAX_BYTES
from main import app
from shared.dependencies.rate_limit import limiter

NOW = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
PASSWORD = "correct horse battery staple"
EMPTY_RESPONSE = {
    "reply": {
        "answer": "I could not find relevant information in the provided documents.",
        "source_ids": [],
    },
    "sources": [],
    "evaluation": {
        "sentences": [],
        "metrics": {
            "groundedness_score": 0,
            "verified_sentences": 0,
            "unsupported_claims": 0,
            "total_sentences": 0,
            "citation_count": 0,
        },
    },
}


@pytest.fixture(autouse=True)
def isolated_app():
    previous_rate_limit_state = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous_rate_limit_state
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _authenticate(client: TestClient) -> Administrator:
    repository = InMemoryAdministratorAuthRepository()
    service = AdministratorAuthenticationService(
        repository,
        AdministratorPasswordService(),
        session_ttl_seconds=3600,
        login_max_failures=3,
        login_lockout_seconds=300,
        clock=lambda: NOW,
        token_factory=lambda: "rag-ui-browser-session",
    )
    service.bootstrap("admin@example.com", PASSWORD)
    login = service.login("admin@example.com", PASSWORD)
    app.dependency_overrides[get_administrator_auth_service] = lambda: service
    client.cookies.set("redmoor_admin_session", login.session_token)
    return login.administrator


def test_rag_routes_reject_anonymous_callers_before_sensitive_work(client, monkeypatch):
    monkeypatch.setattr(
        "assistant.api.rag.rag_chat",
        lambda **_kwargs: pytest.fail("anonymous request reached RAG orchestration"),
    )
    monkeypatch.setattr(
        "assistant.api.audit.get_audit_logs",
        lambda _limit: pytest.fail("anonymous request reached audit persistence"),
    )

    rag_response = client.post("/rag-chat", json={"message": "hello"})
    audit_response = client.get("/audit-logs")

    assert rag_response.status_code == 401
    assert audit_response.status_code == 401
    assert rag_response.headers["cache-control"] == "no-store"
    assert audit_response.headers["cache-control"] == "no-store"


def test_production_authorization_uses_trusted_legacy_rag_policy(client, monkeypatch):
    _authenticate(client)
    retrieval_roles = []
    doctor_chunk = {
        "id": "doctor-chunk",
        "doc_id": "doctor-document",
        "text": "Doctor-only policy",
        "distance": 0.1,
        "keyword_match": 0.5,
        "hybrid_score": 0.9,
    }
    reply = {
        "answer": "Doctor-only answer",
        "source_ids": [doctor_chunk["id"]],
    }
    evaluation = {"sentences": [], "metrics": {"total_sentences": 0}}

    monkeypatch.setattr("assistant.application.rag_chat.DEBUG_DELAY", False)
    monkeypatch.setattr("assistant.application.rag_chat.DISABLE_AUDIT_LOGS", True)
    monkeypatch.setattr("assistant.application.rag_chat.get_cached_response", lambda *_args: None)

    def retrieve(_query, role, _start_time, _repository):
        retrieval_roles.append(role)
        return ([doctor_chunk] if role == "doctor" else [], [], 0.1)

    monkeypatch.setattr("assistant.application.rag_chat.retrieve_context", retrieve)
    monkeypatch.setattr(
        "assistant.application.rag_chat.generate_answer",
        lambda _query, results: (reply, results, results, 0.1),
    )
    monkeypatch.setattr(
        "assistant.application.rag_chat.build_evaluation", lambda *_args: evaluation
    )
    monkeypatch.setattr("assistant.application.rag_chat.set_cache", lambda *_args: None)

    allowed = client.post(
        "/rag-chat",
        json={"message": "allowed", "user_role": "doctor"},
    )
    forged = client.post("/rag-chat", json={"message": "forged", "user_role": "administrator"})
    unknown = client.post("/rag-chat", json={"message": "unknown", "user_role": "unknown-role"})
    omitted = client.post("/rag-chat", json={"message": "omitted"})

    assert allowed.status_code == 200
    assert allowed.json()["sources"] == [{"id": "doctor-chunk", "text": "Doctor-only policy"}]
    assert forged.status_code == 403
    assert unknown.status_code == 403
    assert omitted.status_code == 200
    assert omitted.json()["reply"]["answer"] == "Doctor-only answer"
    assert retrieval_roles == ["doctor", "doctor"]


def test_cached_answer_cannot_cross_effective_role_boundaries(client, monkeypatch):
    _authenticate(client)
    cache_lookups = []
    manager_answer = {
        "reply": {"answer": "Manager-only answer", "source_ids": ["manager-chunk"]},
        "sources": [{"id": "manager-chunk", "text": "Restricted manager text"}],
        "evaluation": None,
    }
    monkeypatch.setattr("assistant.application.rag_chat.DEBUG_DELAY", False)
    monkeypatch.setattr("assistant.application.rag_chat.DISABLE_CACHE", False)

    def get_cached_value(_query, role):
        cache_lookups.append(role)
        return manager_answer if role == "manager" else None

    monkeypatch.setattr("assistant.application.rag_chat.get_cache", get_cached_value)
    monkeypatch.setattr(
        "assistant.application.rag_chat.get_latest_audit_log_for_query", lambda **_kwargs: None
    )
    monkeypatch.setattr(
        "assistant.application.rag_chat.retrieve_context", lambda *_args: ([], [], 0.1)
    )

    privileged = client.post("/rag-chat", json={"message": "policy", "user_role": "manager"})
    narrower = client.post("/rag-chat", json={"message": "policy", "user_role": "doctor"})
    omitted = client.post("/rag-chat", json={"message": "policy"})

    assert privileged.status_code == 200
    assert privileged.json() == manager_answer
    assert narrower.status_code == 200
    assert narrower.json() == EMPTY_RESPONSE
    assert "Manager-only answer" not in narrower.text
    assert omitted.status_code == 200
    assert omitted.json() == EMPTY_RESPONSE
    assert cache_lookups == ["manager", "doctor", "doctor"]


def test_authenticated_caller_without_admin_authorization_cannot_read_audit(client):
    _authenticate(client)

    def reject_role():
        raise admin_auth_error(AdminAuthErrorCode.forbidden)

    app.dependency_overrides[require_administrator_role] = reject_role

    response = client.get("/audit-logs")

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_rag_message_and_raw_request_body_are_bounded(client, monkeypatch):
    _authenticate(client)
    monkeypatch.setattr("assistant.api.rag.rag_chat", lambda **_kwargs: EMPTY_RESPONSE)
    body_prefix = b'{"message":"hello","padding":"'
    body_suffix = b'"}'
    maximum_body = (
        body_prefix
        + b"x" * (RAG_UI_REQUEST_MAX_BYTES - len(body_prefix) - len(body_suffix))
        + body_suffix
    )

    maximum = client.post("/rag-chat", json={"message": "x" * MAX_RAG_MESSAGE_CHARACTERS})
    oversized_message = client.post(
        "/rag-chat", json={"message": "x" * (MAX_RAG_MESSAGE_CHARACTERS + 1)}
    )
    maximum_raw_body = client.post(
        "/rag-chat",
        content=maximum_body,
        headers={"Content-Type": "application/json"},
    )
    oversized_body = client.post(
        "/rag-chat",
        content=maximum_body + b" ",
        headers={"Content-Type": "application/json"},
    )

    assert maximum.status_code == 200
    assert maximum.headers["cache-control"] == "no-store"
    assert oversized_message.status_code == 422
    assert maximum_raw_body.status_code == 200
    assert oversized_body.status_code == 413


@pytest.mark.parametrize("limit", [0, -1, 201, 10**30, "invalid"])
def test_audit_limit_rejects_values_outside_the_bounded_range(client, limit):
    _authenticate(client)

    response = client.get("/audit-logs", params={"limit": limit})

    assert response.status_code == 422


def test_authorized_debug_responses_are_no_store_and_errors_are_safe(client, monkeypatch, caplog):
    _authenticate(client)
    secret = "fictional-password=do-not-return"
    monkeypatch.setattr(
        "assistant.api.rag.rag_chat", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret))
    )
    monkeypatch.setattr(
        "assistant.api.audit.get_audit_logs",
        lambda _limit: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    rag_response = client.post("/rag-chat", json={"message": "hello"})
    audit_response = client.get("/audit-logs")

    assert rag_response.status_code == 500
    assert audit_response.status_code == 500
    assert rag_response.json() == {"detail": "Internal server error"}
    assert audit_response.json() == {"detail": "Internal server error"}
    assert secret not in rag_response.text
    assert secret not in audit_response.text
    assert secret not in caplog.text
    assert rag_response.headers["cache-control"] == "no-store"
    assert audit_response.headers["cache-control"] == "no-store"
