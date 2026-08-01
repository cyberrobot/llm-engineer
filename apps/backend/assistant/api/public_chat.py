import json
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from assistant.api.dependencies import get_public_chat_service
from assistant.application.public_chat import PreparedPublicChat, PublicAssistantChatService
from assistant.domain.assistant_repository import AssistantNotFound
from assistant.schemas.public_chat import (
    MAX_PUBLIC_CHAT_REQUEST_BYTES,
    PublicChatErrorResponse,
    PublicChatRequest,
)
from core.config import get_public_assistant_chat_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse_stream(session: PreparedPublicChat) -> Iterator[str]:
    for event in session.events():
        data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
        yield f"event: {event.type}\ndata: {data}\n\n"


async def require_public_chat_enabled(request: Request) -> None:
    if not get_public_assistant_chat_settings().enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "chat_unavailable", "message": "Public chat is unavailable."},
        )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            encoded_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_request", "message": "The request is invalid."},
            ) from exc
        if encoded_size < 0 or encoded_size > MAX_PUBLIC_CHAT_REQUEST_BYTES:
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "The chat request is too large."},
            )
    if len(await request.body()) > MAX_PUBLIC_CHAT_REQUEST_BYTES:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "The chat request is too large."},
        )


@router.post(
    "/public/assistants/{assistant_slug}/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE start, delta, complete, or error events.",
        },
        400: {"model": PublicChatErrorResponse, "description": "Invalid request framing"},
        404: {"model": PublicChatErrorResponse, "description": "Assistant not found"},
        422: {"model": PublicChatErrorResponse, "description": "Invalid request"},
        500: {"model": PublicChatErrorResponse, "description": "Chat unavailable"},
        503: {"model": PublicChatErrorResponse, "description": "Public chat disabled"},
    },
    summary="Stream a grounded public assistant response",
    tags=["public assistant"],
    openapi_extra={"security": []},
)
def public_chat(
    assistant_slug: str,
    request: PublicChatRequest,
    _enabled: Annotated[None, Depends(require_public_chat_enabled)],
    service: Annotated[PublicAssistantChatService, Depends(get_public_chat_service)],
) -> StreamingResponse:
    del _enabled
    try:
        session = service.prepare(assistant_slug, request)
    except AssistantNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "assistant_not_found", "message": "Assistant not found."},
        ) from exc
    except Exception as exc:
        logger.error("Public assistant chat preparation failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "chat_unavailable", "message": "Public chat is unavailable."},
        ) from exc

    return StreamingResponse(
        _sse_stream(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
