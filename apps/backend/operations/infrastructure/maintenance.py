import json
from collections.abc import Awaitable, Callable
from typing import Any

from operations.application.administration import MaintenanceService
from operations.domain.administration import OperationsDependencyUnavailable

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]
]


class MaintenanceModeMiddleware:
    """Centrally gate public runtime traffic while leaving admin and probes reachable."""

    _LEGACY_PUBLIC_ASSISTANT_PATHS = frozenset({"/assistant/chat", "/rag-chat"})

    def __init__(self, app: ASGIApp, service_factory: Callable[[], MaintenanceService]) -> None:
        self.app = app
        self._service_factory = service_factory

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self._is_public_assistant_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        try:
            state = self._service_factory().get()
        except OperationsDependencyUnavailable:
            await self._send_error(
                send,
                "maintenance_state_unavailable",
                "Service availability cannot currently be determined.",
            )
            return
        if not state.enabled:
            await self.app(scope, receive, send)
            return
        await self._send_error(
            send,
            "maintenance_mode",
            "The service is undergoing maintenance.",
        )

    @staticmethod
    async def _send_error(send, code: str, message: str) -> None:
        body = json.dumps({"detail": {"code": code, "message": message}}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _is_public_assistant_path(path: str) -> bool:
        return path in MaintenanceModeMiddleware._LEGACY_PUBLIC_ASSISTANT_PATHS or (
            path.startswith("/public/assistants/") and path.endswith("/chat")
        )
