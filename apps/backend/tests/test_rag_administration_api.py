from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.rag_admin import get_rag_chat_handler, router
from core.exceptions import register_exception_handlers


def _client(*, authorized: bool) -> tuple[TestClient, Mock]:
    handler = Mock(
        return_value={
            "reply": {"answer": "Use the approved checklist.", "source_ids": ["chunk-1"]},
            "sources": [{"id": "chunk-1", "text": "Approved checklist"}],
            "evaluation": {"metrics": {"groundedness_score": 1.0}},
        }
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_rag_chat_handler] = lambda: handler
    if authorized:
        app.dependency_overrides[require_administrator_role] = lambda: object()
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app), handler


def test_rag_chat_requires_an_authorized_administrator_before_work() -> None:
    client, handler = _client(authorized=False)

    response = client.post(
        "/admin/assistants/rag-chat",
        json={"message": "What is required?", "user_role": "manager"},
    )

    assert response.status_code == 401
    handler.assert_not_called()


def test_authorized_rag_chat_preserves_the_rag_ui_contract() -> None:
    client, handler = _client(authorized=True)

    response = client.post(
        "/admin/assistants/rag-chat",
        json={"message": "What is required?", "user_role": "manager"},
    )

    assert response.status_code == 200
    assert response.json()["reply"]["answer"] == "Use the approved checklist."
    assert response.json()["sources"] == [{"id": "chunk-1", "text": "Approved checklist"}]
    assert response.json()["evaluation"]["metrics"]["groundedness_score"] == 1.0
    handler.assert_called_once_with(query="What is required?", user_role="manager")


def test_rag_chat_rejects_unrecognized_retrieval_roles_without_work() -> None:
    client, handler = _client(authorized=True)

    response = client.post(
        "/admin/assistants/rag-chat",
        json={"message": "What is required?", "user_role": "administrator"},
    )

    assert response.status_code == 422
    handler.assert_not_called()


def test_rag_chat_maps_internal_failures_to_a_safe_error() -> None:
    client, handler = _client(authorized=True)
    handler.side_effect = RuntimeError("provider secret and internal host")

    response = client.post(
        "/admin/assistants/rag-chat",
        json={"message": "What is required?", "user_role": "doctor"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "rag_chat_unavailable",
            "message": "The RAG chat request could not be completed.",
        }
    }
    assert "provider secret" not in response.text
