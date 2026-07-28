from fastapi.testclient import TestClient

from assistant.api.dependencies import get_chat_service
from assistant.schemas import ChatRequest, ChatResponse


class RecordingChatService:
    def __init__(self) -> None:
        self.request: ChatRequest | None = None

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.request = request
        return ChatResponse(
            message="Assistant backend connected successfully.",
            sources=[],
        )


def create_client(monkeypatch) -> tuple[TestClient, RecordingChatService]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    from main import app

    service = RecordingChatService()
    app.dependency_overrides[get_chat_service] = lambda: service
    return TestClient(app), service


def test_chat_returns_mock_response_and_delegates_validated_request(monkeypatch):
    client, service = create_client(monkeypatch)

    response = client.post("/assistant/chat", json={"message": "  Hello  "})

    assert response.status_code == 200
    assert response.json() == {
        "message": "Assistant backend connected successfully.",
        "sources": [],
    }
    assert service.request == ChatRequest(message="Hello")


def test_chat_rejects_request_without_message(monkeypatch):
    client, service = create_client(monkeypatch)

    response = client.post("/assistant/chat", json={})

    assert response.status_code == 422
    assert service.request is None


def test_chat_rejects_empty_message(monkeypatch):
    client, service = create_client(monkeypatch)

    response = client.post("/assistant/chat", json={"message": ""})

    assert response.status_code == 422
    assert service.request is None


def test_chat_rejects_whitespace_and_additional_fields(monkeypatch):
    client, service = create_client(monkeypatch)

    whitespace_response = client.post("/assistant/chat", json={"message": "  \n"})
    extra_field_response = client.post(
        "/assistant/chat",
        json={"message": "Hello", "conversation_id": "not-supported"},
    )

    assert whitespace_response.status_code == 422
    assert extra_field_response.status_code == 422
    assert service.request is None
