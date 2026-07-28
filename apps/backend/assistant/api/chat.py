from typing import Annotated

from fastapi import APIRouter, Depends

from assistant.api.dependencies import get_chat_service
from assistant.application.chat import ChatService
from assistant.schemas import ChatRequest, ChatResponse, ErrorResponse

router = APIRouter()


@router.post(
    "/assistant/chat",
    response_model=ChatResponse,
    responses={
        429: {"model": ErrorResponse, "description": "AI provider rate limit"},
        502: {"model": ErrorResponse, "description": "AI provider request failure"},
        503: {"model": ErrorResponse, "description": "AI provider unavailable"},
        504: {"model": ErrorResponse, "description": "AI provider timeout"},
    },
    summary="Send a message to the Assistant",
    tags=["assistant"],
)
def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    return service.chat(request)
