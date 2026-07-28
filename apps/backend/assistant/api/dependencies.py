from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from assistant.application.chat import ChatService
from infrastructure.ai import AIProvider, create_ai_provider


@lru_cache
def get_ai_provider() -> AIProvider:
    """Provide the configured AI adapter at the application boundary."""
    return create_ai_provider()


def get_chat_service(
    ai_provider: Annotated[AIProvider, Depends(get_ai_provider)],
) -> ChatService:
    """Provide the application service used by Assistant chat routes."""
    return ChatService(ai_provider)
