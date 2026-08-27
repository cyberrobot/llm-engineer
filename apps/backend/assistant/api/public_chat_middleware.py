import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.config import get_public_assistant_chat_settings
from core.metrics import public_chat_metrics

logger = logging.getLogger(__name__)

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]
]


class PublicChatBoundaryMiddleware:
    """Enforce the anonymous Assistant gate and strict route-specific CORS."""

    _ALLOWED_HEADERS = {"content-type", "x-anonymous-session-id", "x-request-id"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route_kind = self._public_route_kind(scope.get("path", ""))
        if route_kind is None:
            await self.app(scope, receive, send)
            return
        expected_method = "POST" if route_kind == "chat" else "GET"
        settings = get_public_assistant_chat_settings()
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", ())
        }
        origin = headers.get("origin")
        if not settings.enabled:
            await self._json_error(
                send,
                503,
                "public_chat_unavailable",
                "Public chat is unavailable.",
                origin=origin if origin in settings.allowed_origins else None,
                method=expected_method,
            )
            return
        if origin is not None and origin not in settings.allowed_origins:
            public_chat_metrics.origin_rejections.inc()
            logger.warning("public_chat_origin_rejected", extra={"origin": origin[:256]})
            await self._json_error(send, 403, "origin_not_allowed", "Origin is not allowed.")
            return
        if scope["method"] == "OPTIONS":
            requested_method = headers.get("access-control-request-method", "").upper()
            requested_headers = {
                item.strip().lower()
                for item in headers.get("access-control-request-headers", "").split(",")
                if item.strip()
            }
            if (
                origin is None
                or requested_method != expected_method
                or not requested_headers.issubset(self._ALLOWED_HEADERS)
            ):
                await self._json_error(
                    send, 403, "origin_not_allowed", "CORS preflight is not allowed."
                )
                return
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": self._cors_headers(origin, expected_method),
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return
        if scope["method"] != expected_method:
            await self.app(scope, receive, send)
            return
        if route_kind == "configuration":
            await self.app(scope, receive, self._cors_sender(send, origin, expected_method))
            return
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            await self._json_error(
                send,
                415,
                "unsupported_media_type",
                "Content-Type must be application/json.",
                origin=origin,
            )
            return
        declared = headers.get("content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                await self._json_error(send, 400, "invalid_request", "The request is invalid.")
                return
            if declared_size < 0 or declared_size > settings.maximum_request_bytes:
                public_chat_metrics.request_bytes.observe(max(0, declared_size))
                public_chat_metrics.payload_rejections.inc()
                await self._json_error(
                    send,
                    413,
                    "request_too_large",
                    "The request is too large.",
                    origin=origin,
                )
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > settings.maximum_request_bytes:
                public_chat_metrics.request_bytes.observe(len(body))
                public_chat_metrics.payload_rejections.inc()
                await self._json_error(
                    send,
                    413,
                    "request_too_large",
                    "The request is too large.",
                    origin=origin,
                )
                return
            more_body = bool(message.get("more_body", False))
        public_chat_metrics.request_bytes.observe(len(body))

        delivered = False

        async def replay_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_receive, self._cors_sender(send, origin, expected_method))

    @staticmethod
    def _public_route_kind(path: str) -> str | None:
        prefix = "/public/assistants/"
        if not path.startswith(prefix):
            return None
        remainder = path.removeprefix(prefix)
        if remainder and "/" not in remainder:
            return "configuration"
        if remainder.endswith("/chat") and "/" not in remainder.removesuffix("/chat"):
            return "chat"
        return None

    @classmethod
    def _cors_headers(cls, origin: str, method: str) -> list[tuple[bytes, bytes]]:
        return [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-methods", f"{method}, OPTIONS".encode("ascii")),
            (
                b"access-control-allow-headers",
                b"Content-Type, X-Anonymous-Session-ID, X-Request-ID",
            ),
            (b"access-control-expose-headers", b"X-Request-ID, Retry-After"),
            (b"vary", b"Origin"),
        ]

    @classmethod
    def _cors_sender(cls, send, origin: str | None, method: str):
        async def cors_send(message):
            if message["type"] == "http.response.start" and origin is not None:
                message = dict(message)
                inner_headers = [
                    (key, value)
                    for key, value in message.get("headers", ())
                    if not key.lower().startswith(b"access-control-")
                ]
                message["headers"] = inner_headers + cls._cors_headers(origin, method)
            await send(message)

        return cors_send

    async def _json_error(
        self,
        send,
        status: int,
        code: str,
        message: str,
        *,
        origin: str | None = None,
        method: str = "POST",
    ) -> None:
        body = json.dumps({"detail": {"code": code, "message": message}}).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store"),
        ]
        if origin is not None:
            headers.extend(self._cors_headers(origin, method))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
