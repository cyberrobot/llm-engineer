from typing import Annotated

from fastapi import APIRouter, Depends

from assistant.api.dependencies import get_chat_service
from assistant.application.chat import ChatService
from assistant.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post(
    "/assistant/chat",
    response_model=ChatResponse,
    summary="Send a message to the Assistant",
    tags=["assistant"],
)
def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    return service.chat(request)
