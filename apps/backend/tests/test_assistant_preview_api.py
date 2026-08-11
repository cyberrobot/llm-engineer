import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_behaviour import router
from assistant.api.dependencies import get_assistant_preview_chat_service
from assistant.application.public_chat import AssistantPreviewChatService
from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from assistant.infrastructure.repositories.assistant_behaviour import (
    InMemoryAssistantBehaviourRepository,
)
from core.config import PublicAssistantChatSettings
from core.exceptions import register_exception_handlers
from infrastructure.ai.providers import AIProvider

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
ASSISTANT_ID = UUID("11111111-1111-4111-8111-111111111111")


class Provider(AIProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "test"

    @property
    def model(self) -> str:
        return "test-model"

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("preview must stream")

    def stream_response(self, *, system_prompt: str, user_prompt: str, **_kwargs):
        self.calls.append((system_prompt, user_prompt))
        yield "Draft answer"


class RetrievalFactory:
    def __init__(self) -> None:
        self.assistant_ids: list[UUID] = []

    def __call__(self, assistant_id: UUID):
        self.assistant_ids.append(assistant_id)

        class Retrieval:
            def retrieve(self, query: str):
                assert query == "Current question"
                return [
                    KnowledgeChunk(
                        id="chunk",
                        document=KnowledgeDocument(id="document", title="Private knowledge"),
                        content="Grounded fact",
                        score=1.0,
                    )
                ]

        return Retrieval()


def parse_events(body: str) -> list[tuple[str, dict]]:
    return [
        (frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
        for frame in body.strip().split("\n\n")
    ]


def setup(*, authenticated: bool = True, trusted: bool = True):
    assistant = Assistant(
        ASSISTANT_ID,
        "private-preview",
        "Private Preview",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        NOW,
        NOW,
    )
    assistants = InMemoryAssistantRepository((assistant,))
    behaviours = InMemoryAssistantBehaviourRepository(assistants)
    initial = behaviours.get_state(ASSISTANT_ID)
    behaviours.save_draft(
        ASSISTANT_ID,
        expected_token=initial.concurrency_token,
        instructions="Use the saved draft style.",
        welcome_message="",
        input_placeholder="Ask",
        suggested_questions=(),
        at=NOW,
    )
    provider = Provider()
    retrievals = RetrievalFactory()
    service = AssistantPreviewChatService(
        assistants,
        behaviours,
        retrievals,
        provider,
        settings=PublicAssistantChatSettings.development_defaults(enabled=True),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_assistant_preview_chat_service] = lambda: service
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    if trusted:
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app), behaviours, provider, retrievals


def test_preview_allows_inactive_private_assistant_and_uses_saved_draft_without_mutation() -> None:
    api, behaviours, provider, retrievals = setup()
    before = behaviours.get_state(ASSISTANT_ID)
    response = api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={
            "message": "Current question",
            "history": [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            ],
        },
    )
    assert response.status_code == 200
    assert parse_events(response.text) == [
        ("start", {"assistant": "private-preview"}),
        ("delta", {"text": "Draft answer"}),
        ("complete", {"finishReason": "stop"}),
    ]
    assert retrievals.assistant_ids == [ASSISTANT_ID]
    assert len(provider.calls) == 1
    assert "Use the saved draft style." in provider.calls[0][0]
    assert "Earlier question" in provider.calls[0][1]
    assert behaviours.get_state(ASSISTANT_ID) == before


def test_preview_requires_authentication_and_trusted_origin() -> None:
    unauthenticated, *_ = setup(authenticated=False)
    assert (
        unauthenticated.post(
            f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
            json={"message": "Current question"},
        ).status_code
        == 401
    )
    untrusted, *_ = setup(trusted=False)
    assert (
        untrusted.post(
            f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
            json={"message": "Current question"},
        ).status_code
        == 403
    )
