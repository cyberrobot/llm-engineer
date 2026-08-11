import json
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_behaviour import router
from assistant.api.dependencies import get_assistant_preview_chat_service
from assistant.application.public_chat import AssistantPreviewChatService
from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourNotFound
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from assistant.infrastructure.repositories.assistant_behaviour import (
    InMemoryAssistantBehaviourRepository,
)
from assistant.schemas.public_chat import PublicChatRequest
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
    def __init__(self, *, chunks: bool = True, after_retrieve=None) -> None:
        self.assistant_ids: list[UUID] = []
        self.chunks = chunks
        self.after_retrieve = after_retrieve

    def __call__(self, assistant_id: UUID):
        self.assistant_ids.append(assistant_id)

        class Retrieval:
            def retrieve(self, query: str):
                assert query == "Current question"
                if self_factory.after_retrieve is not None:
                    self_factory.after_retrieve()
                if not self_factory.chunks:
                    return []
                return [
                    KnowledgeChunk(
                        id="chunk",
                        document=KnowledgeDocument(id="document", title="Private knowledge"),
                        content="Grounded fact",
                        score=1.0,
                    )
                ]

        self_factory = self
        return Retrieval()


def parse_events(body: str) -> list[tuple[str, dict]]:
    return [
        (frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
        for frame in body.strip().split("\n\n")
    ]


def setup(
    *,
    authenticated: bool = True,
    trusted: bool = True,
    provider: Provider | None = None,
    retrievals: RetrievalFactory | None = None,
    settings: PublicAssistantChatSettings | None = None,
    clock=None,
    behaviour_unavailable: bool = False,
):
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
    provider = provider or Provider()
    retrievals = retrievals or RetrievalFactory()

    class UnavailableBehaviours:
        def get_state(self, assistant_id):
            del assistant_id
            raise AssistantBehaviourNotFound("Behaviour unavailable")

    service = AssistantPreviewChatService(
        assistants,
        UnavailableBehaviours() if behaviour_unavailable else behaviours,  # type: ignore[arg-type]
        retrievals,
        provider,
        settings=settings or PublicAssistantChatSettings.development_defaults(enabled=True),
        clock=clock or perf_counter,
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_assistant_preview_chat_service] = lambda: service
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    if trusted:
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app), behaviours, provider, retrievals, service


def test_preview_allows_inactive_private_assistant_and_uses_saved_draft_without_mutation() -> None:
    api, behaviours, provider, retrievals, _service = setup()
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


def test_preview_documents_all_non_streaming_error_responses() -> None:
    api, *_ = setup()
    operation = api.app.openapi()["paths"]["/admin/assistants/{assistant_id}/preview/chat"]["post"]
    assert {"401", "403", "404", "409", "422", "504"}.issubset(operation["responses"])


def test_preview_returns_safe_not_found_and_behaviour_unavailable_errors() -> None:
    api, *_ = setup()
    missing = api.post(
        "/admin/assistants/22222222-2222-4222-8222-222222222222/preview/chat",
        json={"message": "Current question"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "assistant_not_found"

    unavailable, *_ = setup(behaviour_unavailable=True)
    response = unavailable.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "assistant_preview_unavailable",
        "message": "Assistant preview is unavailable.",
    }


def test_preview_rejects_invalid_history_and_excessive_prompt_without_mutation() -> None:
    api, behaviours, provider, _retrievals, _service = setup()
    before = behaviours.get_state(ASSISTANT_ID)
    invalid_history = api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question", "history": [{"role": "user", "content": "open"}]},
    )
    assert invalid_history.status_code == 422

    tiny_budget = replace(
        PublicAssistantChatSettings.development_defaults(enabled=True), maximum_input_tokens=1
    )
    limited, limited_behaviours, limited_provider, *_ = setup(settings=tiny_budget)
    limited_before = limited_behaviours.get_state(ASSISTANT_ID)
    excessive = limited.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert excessive.status_code == 422
    assert excessive.json()["detail"]["code"] == "input_token_limit_exceeded"
    assert provider.calls == limited_provider.calls == []
    assert behaviours.get_state(ASSISTANT_ID) == before
    assert limited_behaviours.get_state(ASSISTANT_ID) == limited_before


def test_preview_preparation_timeout_is_safe_and_does_not_mutate() -> None:
    class Clock:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Clock()
    retrievals = RetrievalFactory(after_retrieve=lambda: setattr(clock, "value", 60.0))
    api, behaviours, provider, *_ = setup(retrievals=retrievals, clock=clock)
    before = behaviours.get_state(ASSISTANT_ID)
    response = api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert response.status_code == 504
    assert response.json()["detail"] == {
        "code": "request_timed_out",
        "message": "The response could not be completed.",
    }
    assert provider.calls == []
    assert behaviours.get_state(ASSISTANT_ID) == before


def test_preview_streams_safe_provider_failure_and_timeout_without_prompt_leakage() -> None:
    class FailingProvider(Provider):
        def stream_response(self, **kwargs):
            del kwargs
            yield "partial"
            raise RuntimeError("Use the saved draft style. provider-secret")

    failing_api, behaviours, _provider, *_ = setup(provider=FailingProvider())
    before = behaviours.get_state(ASSISTANT_ID)
    failed = failing_api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert parse_events(failed.text)[-1] == (
        "error",
        {"code": "generation_failed", "message": "The response could not be completed."},
    )
    assert "provider-secret" not in failed.text
    assert "saved draft" not in failed.text.lower()
    assert behaviours.get_state(ASSISTANT_ID) == before

    class Clock:
        value = 0.0

        def __call__(self):
            return self.value

    clock = Clock()

    class TimingOutProvider(Provider):
        def stream_response(self, **kwargs):
            del kwargs
            clock.value = 60.0
            yield "late secret"

    timeout_api, timeout_behaviours, *_ = setup(provider=TimingOutProvider(), clock=clock)
    timeout_before = timeout_behaviours.get_state(ASSISTANT_ID)
    timed_out = timeout_api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert parse_events(timed_out.text)[-1] == (
        "error",
        {"code": "request_timed_out", "message": "The response could not be completed."},
    )
    assert "late secret" not in timed_out.text
    assert timeout_behaviours.get_state(ASSISTANT_ID) == timeout_before


def test_preview_without_knowledge_bypasses_provider_and_preserves_publication() -> None:
    api, behaviours, provider, *_ = setup(retrievals=RetrievalFactory(chunks=False))
    before = behaviours.get_state(ASSISTANT_ID)
    response = api.post(
        f"/admin/assistants/{ASSISTANT_ID}/preview/chat",
        json={"message": "Current question"},
    )
    assert parse_events(response.text) == [
        ("start", {"assistant": "private-preview"}),
        (
            "delta",
            {
                "text": "I don’t have enough information in this assistant’s knowledge base to answer that."
            },
        ),
        ("complete", {"finishReason": "stop"}),
    ]
    assert provider.calls == []
    assert behaviours.get_state(ASSISTANT_ID) == before


def test_prepared_preview_keeps_resolved_draft_while_next_request_uses_newer_draft() -> None:
    _api, behaviours, provider, _retrievals, service = setup()
    prepared = service.prepare(ASSISTANT_ID, PublicChatRequest(message="Current question"))
    current = behaviours.get_state(ASSISTANT_ID)
    behaviours.save_draft(
        ASSISTANT_ID,
        expected_token=current.concurrency_token,
        instructions="NEWER DRAFT INSTRUCTIONS",
        welcome_message="",
        input_placeholder="Ask",
        suggested_questions=(),
        at=NOW,
    )
    list(prepared.events())
    assert "Use the saved draft style." in provider.calls[-1][0]
    assert "NEWER DRAFT INSTRUCTIONS" not in provider.calls[-1][0]
    list(
        service.prepare(
            ASSISTANT_ID,
            PublicChatRequest(message="Current question"),
        ).events()
    )
    assert "NEWER DRAFT INSTRUCTIONS" in provider.calls[-1][0]
