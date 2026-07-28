from assistant.schemas import ChatRequest, ChatResponse
from infrastructure.ai.providers import AIProvider

SYSTEM_PROMPT = "You are a professional business discovery assistant."


class ChatService:
    """Handle Assistant chat requests."""

    def __init__(self, ai_provider: AIProvider) -> None:
        self._ai_provider = ai_provider

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Validate and orchestrate a single stateless Assistant response."""
        user_prompt = request.message.strip()
        if not user_prompt:
            raise ValueError("Chat message must not be empty")

        message = self._ai_provider.generate_response(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return ChatResponse(
            message=message,
            sources=[],
        )
