from assistant.application.chat import SYSTEM_PROMPT, ChatService
from assistant.schemas import ChatRequest
from infrastructure.ai.providers import AIProvider


class StubAIProvider(AIProvider):
    def __init__(self) -> None:
        self.call: tuple[str, str] | None = None

    @property
    def name(self) -> str:
        return "stub"

    @property
    def model(self) -> str:
        return "stub-model"

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        self.call = (system_prompt, user_prompt)
        return "Generated response"


def test_chat_service_orchestrates_provider_and_maps_response():
    provider = StubAIProvider()
    service = ChatService(provider)

    response = service.chat(ChatRequest(message="What should we discover?"))

    assert provider.call == (SYSTEM_PROMPT, "What should we discover?")
    assert response.message == "Generated response"
    assert response.sources == []
