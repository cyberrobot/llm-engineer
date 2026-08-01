import json
import logging
import threading
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from assistant.api.dependencies import (
    get_public_chat_protection,
    get_public_chat_service_factory,
)
from assistant.application.public_chat import (
    PreparedPublicChat,
    PublicAssistantChatService,
    PublicChatInputLimitExceeded,
    PublicChatRequestTimedOut,
)
from assistant.application.public_chat_protection import (
    PublicChatProtection,
    PublicChatRejected,
    PublicChatRequestPermit,
)
from assistant.domain.assistant_repository import AssistantNotFound
from assistant.schemas.public_chat import (
    PublicChatErrorResponse,
    PublicChatRequest,
)
from core.config import get_public_assistant_chat_settings
from core.metrics import public_chat_metrics

logger = logging.getLogger(__name__)
router = APIRouter()


class _RequestCleanup:
    def __init__(self, permit: PublicChatRequestPermit) -> None:
        self._permit = permit
        self._done = False
        self._lock = threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self._permit.release()
        public_chat_metrics.active.dec()


def _sse_stream(session: PreparedPublicChat, cleanup: _RequestCleanup) -> Iterator[str]:
    events = session.events()
    try:
        for event in events:
            data = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event.type}\ndata: {data}\n\n"
    finally:
        close = getattr(events, "close", None)
        if close is not None:
            close()
        cleanup()


def _rejection(exc: PublicChatRejected) -> HTTPException:
    headers = None
    if exc.retry_after_seconds:
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
        headers=headers,
    )


async def require_public_chat_enabled(request: Request) -> None:
    settings = get_public_assistant_chat_settings()
    if not settings.enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "public_chat_unavailable",
                "message": "Public chat is unavailable.",
            },
        )
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        public_chat_metrics.origin_rejections.inc()
        logger.warning("public_chat_origin_rejected", extra={"origin": origin[:256]})
        raise HTTPException(
            status_code=403,
            detail={"code": "origin_not_allowed", "message": "Origin is not allowed."},
        )
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=415,
            detail={
                "code": "unsupported_media_type",
                "message": "Content-Type must be application/json.",
            },
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
        if encoded_size < 0 or encoded_size > settings.maximum_request_bytes:
            raise HTTPException(
                status_code=413,
                detail={"code": "request_too_large", "message": "The request is too large."},
            )
    request_size = len(await request.body())
    if request_size > settings.maximum_request_bytes:
        logger.warning("public_chat_request_too_large")
        raise HTTPException(
            status_code=413,
            detail={"code": "request_too_large", "message": "The request is too large."},
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
        403: {"model": PublicChatErrorResponse, "description": "Origin not allowed"},
        404: {"model": PublicChatErrorResponse, "description": "Assistant not found"},
        413: {"model": PublicChatErrorResponse, "description": "Request too large"},
        415: {"model": PublicChatErrorResponse, "description": "Unsupported media type"},
        429: {"model": PublicChatErrorResponse, "description": "Public request limit reached"},
        422: {"model": PublicChatErrorResponse, "description": "Invalid request"},
        504: {"model": PublicChatErrorResponse, "description": "Request timed out"},
        500: {"model": PublicChatErrorResponse, "description": "Chat unavailable"},
        503: {"model": PublicChatErrorResponse, "description": "Public chat disabled"},
    },
    summary="Stream a grounded public assistant response",
    tags=["public assistant"],
    openapi_extra={"security": []},
)
def public_chat(
    assistant_slug: str,
    chat_request: PublicChatRequest,
    http_request: Request,
    _enabled: Annotated[None, Depends(require_public_chat_enabled)],
    protection: Annotated[PublicChatProtection, Depends(get_public_chat_protection)],
    service_factory: Annotated[
        Callable[[], PublicAssistantChatService], Depends(get_public_chat_service_factory)
    ],
) -> StreamingResponse:
    del _enabled
    try:
        protection.validate_request(chat_request)
        permit = protection.acquire(
            peer_ip=http_request.client.host if http_request.client is not None else None,
            forwarded_for=http_request.headers.get("x-forwarded-for"),
            anonymous_session=http_request.headers.get("x-anonymous-session-id"),
        )
    except PublicChatRejected as exc:
        if exc.code == "rate_limit_exceeded":
            public_chat_metrics.rate_limit_rejections.inc()
            logger.warning(
                "public_chat_rate_limited",
                extra={"client_key_hash": exc.client_key_hash},
            )
        elif exc.code.endswith("concurrency_limit_exceeded"):
            public_chat_metrics.concurrency_rejections.labels(reason=exc.code).inc()
            logger.warning(
                "public_chat_concurrency_rejected",
                extra={"reason": exc.code, "client_key_hash": exc.client_key_hash},
            )
        raise _rejection(exc) from exc
    public_chat_metrics.active.inc()
    cleanup = _RequestCleanup(permit)
    try:
        service = service_factory()
        session = service.prepare(assistant_slug, chat_request)
    except AssistantNotFound as exc:
        cleanup()
        raise HTTPException(
            status_code=404,
            detail={"code": "assistant_not_found", "message": "Assistant not found."},
        ) from exc
    except PublicChatInputLimitExceeded as exc:
        cleanup()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "input_token_limit_exceeded",
                "message": "The chat input is too large.",
            },
        ) from exc
    except PublicChatRequestTimedOut as exc:
        cleanup()
        raise HTTPException(
            status_code=504,
            detail={
                "code": "request_timed_out",
                "message": "The response could not be completed.",
            },
        ) from exc
    except Exception as exc:
        cleanup()
        logger.error("Public assistant chat preparation failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "public_chat_unavailable",
                "message": "Public chat is unavailable.",
            },
        ) from exc

    return StreamingResponse(
        _sse_stream(session, cleanup),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(cleanup),
    )
