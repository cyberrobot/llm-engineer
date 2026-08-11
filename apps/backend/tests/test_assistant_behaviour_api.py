from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_behaviour import router
from assistant.api.dependencies import get_assistant_behaviour_service
from assistant.application.assistant_behaviour_service import AssistantBehaviourService
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from assistant.infrastructure.repositories.assistant_behaviour import (
    InMemoryAssistantBehaviourRepository,
)
from core.exceptions import register_exception_handlers

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
ASSISTANT_ID = UUID("11111111-1111-4111-8111-111111111111")


def client(*, authenticated: bool = True, trusted: bool = True) -> TestClient:
    assistant = Assistant(
        ASSISTANT_ID,
        "draft",
        "Draft",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        NOW,
        NOW,
    )
    behaviours = InMemoryAssistantBehaviourRepository(InMemoryAssistantRepository((assistant,)))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_assistant_behaviour_service] = lambda: AssistantBehaviourService(
        behaviours, clock=lambda: NOW
    )
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    if trusted:
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app)


def test_get_save_and_publish_return_authoritative_state() -> None:
    api = client()
    initial = api.get(f"/admin/assistants/{ASSISTANT_ID}/behaviour")
    assert initial.status_code == 200
    assert initial.json()["draft"]["revision"] == 1
    assert initial.json()["published"]["revision"] == 1
    assert initial.json()["has_unpublished_changes"] is False

    saved = api.put(
        f"/admin/assistants/{ASSISTANT_ID}/behaviour",
        json={
            "concurrency_token": initial.json()["concurrency_token"],
            "instructions": "  Preserve this exact spacing.  ",
            "welcome_message": "Welcome",
            "input_placeholder": "Ask here",
            "suggested_questions": ["First?", "Second?"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["draft"]["instructions"] == "  Preserve this exact spacing.  "
    assert saved.json()["draft"]["revision"] == 2
    assert saved.json()["published"]["revision"] == 1
    assert saved.json()["has_unpublished_changes"] is True

    stale = api.put(
        f"/admin/assistants/{ASSISTANT_ID}/behaviour",
        json={
            "concurrency_token": initial.json()["concurrency_token"],
            "instructions": "Stale",
            "welcome_message": "",
            "input_placeholder": "Ask",
            "suggested_questions": [],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "assistant_behaviour_update_conflict"

    published = api.post(
        f"/admin/assistants/{ASSISTANT_ID}/behaviour/publish",
        json={
            "concurrency_token": saved.json()["concurrency_token"],
            "draft_revision": 2,
        },
    )
    assert published.status_code == 200
    assert published.json()["published"]["revision"] == 2
    assert published.json()["has_unpublished_changes"] is False


def test_authentication_origin_validation_and_safe_not_found_contracts() -> None:
    assert (
        client(authenticated=False).get(f"/admin/assistants/{ASSISTANT_ID}/behaviour").status_code
        == 401
    )
    denied = client(trusted=False).put(f"/admin/assistants/{ASSISTANT_ID}/behaviour", json={})
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "forbidden"
    missing = client().get("/admin/assistants/22222222-2222-4222-8222-222222222222/behaviour")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "assistant_not_found"


def test_behaviour_validation_rejects_controls_empty_questions_and_extra_fields() -> None:
    api = client()
    token = api.get(f"/admin/assistants/{ASSISTANT_ID}/behaviour").json()["concurrency_token"]
    payload = {
        "concurrency_token": token,
        "instructions": "unsafe\u0000",
        "welcome_message": "",
        "input_placeholder": "two\nlines",
        "suggested_questions": ["  "],
        "unknown": True,
    }
    response = api.put(f"/admin/assistants/{ASSISTANT_ID}/behaviour", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
