from functools import lru_cache

from assistant.application.chat import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    """Provide the application service used by Assistant chat routes."""
    return ChatService()
