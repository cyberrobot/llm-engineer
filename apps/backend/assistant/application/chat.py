from assistant.schemas import ChatRequest, ChatResponse


class ChatService:
    """Handle Assistant chat requests."""

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Return the deterministic response used by the first API integration."""
        return ChatResponse(
            message="Assistant backend connected successfully.",
            sources=[],
        )
