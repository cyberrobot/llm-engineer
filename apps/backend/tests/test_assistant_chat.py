from fastapi.testclient import TestClient

from assistant.api.dependencies import get_ai_provider
from infrastructure.ai.exceptions import AITimeoutError
from infrastructure.ai.providers import AIProvider


class RecordingAIProvider(AIProvider):
    def __init__(self) -> None:
        self.system_prompt: str | None = None
        self.user_prompt: str | None = None
        self.error: Exception | None = None

    @property
    def name(self) -> str:
        return "test"

    @property
    def model(self) -> str:
        return "test-model"

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        if self.error:
            raise self.error
        return "A discovery workshop can clarify your priorities."


def create_client() -> tuple[TestClient, RecordingAIProvider]:
    from main import app

    provider = RecordingAIProvider()
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return TestClient(app), provider


def test_chat_returns_provider_response_and_delegates_validated_request():
    client, provider = create_client()

    response = client.post("/assistant/chat", json={"message": "  Hello  "})

    assert response.status_code == 200
    assert response.json() == {
        "message": "A discovery workshop can clarify your priorities.",
        "sources": [],
    }
    assert provider.user_prompt == (
        "Retrieved knowledge:\nNo relevant knowledge was found.\n\nUser question:\nHello"
    )
    assert provider.system_prompt is not None
    assert "Do not invent facts" in provider.system_prompt


def test_chat_rejects_request_without_message():
    client, provider = create_client()

    response = client.post("/assistant/chat", json={})

    assert response.status_code == 422
    assert provider.user_prompt is None


def test_chat_rejects_empty_message():
    client, provider = create_client()

    response = client.post("/assistant/chat", json={"message": ""})

    assert response.status_code == 422
    assert provider.user_prompt is None


def test_chat_rejects_whitespace_and_additional_fields():
    client, provider = create_client()

    whitespace_response = client.post("/assistant/chat", json={"message": "  \n"})
    extra_field_response = client.post(
        "/assistant/chat",
        json={"message": "Hello", "conversation_id": "not-supported"},
    )

    assert whitespace_response.status_code == 422
    assert extra_field_response.status_code == 422
    assert provider.user_prompt is None


def test_chat_maps_provider_timeout_to_gateway_timeout():
    client, provider = create_client()
    provider.error = AITimeoutError()

    response = client.post("/assistant/chat", json={"message": "Hello"})

    assert response.status_code == 504
    assert response.json() == {"detail": "The AI provider timed out."}
