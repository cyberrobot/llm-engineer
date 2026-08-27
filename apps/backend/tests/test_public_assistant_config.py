from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from assistant.api.dependencies import get_public_assistant_configuration_service
from assistant.application.public_assistant import PublicAssistantConfigurationService
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourNotFound
from assistant.domain.assistant_repository import AssistantNotFound
from assistant.infrastructure.repositories.assistant_behaviour import (
    InMemoryAssistantBehaviourRepository,
)
from main import app


def assistant(
    *,
    slug: str = "redmoor",
    name: str = "Redmoor Assistant",
    status: AssistantStatus = AssistantStatus.active,
    visibility: AssistantVisibility = AssistantVisibility.public,
) -> Assistant:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return Assistant(uuid4(), slug, name, status, visibility, now, now)


class AssistantRepositoryStub:
    def __init__(self, assistants: tuple[Assistant, ...]) -> None:
        self._by_slug = {item.slug: item for item in assistants}

    def get_by_slug(self, slug: str) -> Assistant:
        try:
            return self._by_slug[slug]
        except KeyError as exc:
            raise AssistantNotFound("Assistant not found.") from exc

    def get_by_id(self, assistant_id: UUID) -> Assistant:
        for item in self._by_slug.values():
            if item.id == assistant_id:
                return item
        raise AssistantNotFound("Assistant not found.")


def client_for(service: PublicAssistantConfigurationService) -> TestClient:
    app.dependency_overrides[get_public_assistant_configuration_service] = lambda: service
    return TestClient(app)


def clear_override() -> None:
    app.dependency_overrides.pop(get_public_assistant_configuration_service, None)


def test_public_configuration_returns_published_presentation_and_never_sensitive_fields(
    monkeypatch,
):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    redmoor = assistant()
    assistants = AssistantRepositoryStub((redmoor,))
    behaviours = InMemoryAssistantBehaviourRepository(assistants)  # type: ignore[arg-type]
    initial = behaviours.get_state(redmoor.id)
    saved = behaviours.save_draft(
        redmoor.id,
        expected_token=initial.concurrency_token,
        instructions="PRIVATE DRAFT INSTRUCTIONS",
        welcome_message="Published welcome",
        input_placeholder="Ask Redmoor",
        suggested_questions=("Question one", "Question two"),
        at=initial.updated_at,
    )
    service = PublicAssistantConfigurationService(assistants, behaviours)
    client = client_for(service)
    try:
        before_publish = client.get("/public/assistants/redmoor")
        behaviours.publish(
            redmoor.id,
            expected_token=saved.concurrency_token,
            draft_revision=saved.draft.revision,
            at=saved.updated_at,
        )
        after_publish = client.get("/public/assistants/redmoor")
    finally:
        clear_override()

    assert before_publish.status_code == 200
    assert before_publish.json() == {
        "id": "redmoor",
        "name": "Redmoor Assistant",
        "welcome_message": initial.draft.welcome_message,
        "input_placeholder": initial.draft.input_placeholder,
        "suggested_questions": list(initial.draft.suggested_questions),
        "published_revision": 1,
    }
    assert after_publish.status_code == 200
    assert after_publish.json() == {
        "id": "redmoor",
        "name": "Redmoor Assistant",
        "welcome_message": "Published welcome",
        "input_placeholder": "Ask Redmoor",
        "suggested_questions": ["Question one", "Question two"],
        "published_revision": 2,
    }
    serialized = after_publish.text.lower()
    assert "instructions" not in serialized
    assert "concurrency" not in serialized
    assert "draft" not in serialized
    assert after_publish.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("status", "visibility"),
    [
        (AssistantStatus.inactive, AssistantVisibility.public),
        (AssistantStatus.active, AssistantVisibility.private),
        (AssistantStatus.inactive, AssistantVisibility.private),
    ],
)
def test_public_configuration_hides_missing_and_unavailable_assistants(
    monkeypatch, status, visibility
):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    unavailable = assistant(slug="unavailable", status=status, visibility=visibility)
    assistants = AssistantRepositoryStub((unavailable,))
    service = PublicAssistantConfigurationService(
        assistants,
        InMemoryAssistantBehaviourRepository(assistants),  # type: ignore[arg-type]
    )
    client = client_for(service)
    try:
        unavailable_response = client.get("/public/assistants/unavailable")
        missing_response = client.get("/public/assistants/missing")
    finally:
        clear_override()

    assert unavailable_response.status_code == 404
    assert (
        unavailable_response.json()
        == missing_response.json()
        == {"detail": {"code": "assistant_not_found", "message": "Assistant not found."}}
    )


def test_public_configuration_fails_closed_when_publication_is_missing(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    redmoor = assistant()
    assistants = AssistantRepositoryStub((redmoor,))

    class MissingPublicationRepository:
        def get_published(self, assistant_id: UUID):
            assert assistant_id == redmoor.id
            raise AssistantBehaviourNotFound("private invariant detail")

    service = PublicAssistantConfigurationService(
        assistants,
        MissingPublicationRepository(),  # type: ignore[arg-type]
    )
    client = client_for(service)
    try:
        response = client.get("/public/assistants/redmoor")
    finally:
        clear_override()

    assert response.status_code == 404
    assert response.json() == {
        "detail": {"code": "assistant_not_found", "message": "Assistant not found."}
    }
    assert "invariant" not in response.text


def test_public_configuration_supports_public_cors_without_credentials(monkeypatch):
    monkeypatch.setenv("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
    redmoor = assistant()
    assistants = AssistantRepositoryStub((redmoor,))
    service = PublicAssistantConfigurationService(
        assistants,
        InMemoryAssistantBehaviourRepository(assistants),  # type: ignore[arg-type]
    )
    client = client_for(service)
    try:
        response = client.get(
            "/public/assistants/redmoor", headers={"origin": "http://localhost:5173"}
        )
    finally:
        clear_override()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


def test_public_configuration_openapi_is_anonymous_and_documents_errors():
    app.openapi_schema = None
    schema = app.openapi()
    operation = schema["paths"]["/public/assistants/{assistant_slug}"]["get"]

    assert operation["security"] == []
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PublicAssistantConfigurationResponse"
    }
    assert {"404", "500", "503"}.issubset(operation["responses"])
