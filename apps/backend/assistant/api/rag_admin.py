import logging
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.application.rag_chat import rag_chat
from assistant.schemas.assistant_admin import AssistantAdminErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/assistants",
    tags=["administrator assistant"],
    dependencies=[Depends(require_administrator_role)],
)

RagChatHandler = Callable[..., dict[str, Any]]
RagUiRole = Literal["doctor", "nurse", "analyst", "manager", "agent"]


class RagChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=10_000)
    # This selects the access-role view an administrator is testing. Administrator
    # authentication above is the authorization boundary.
    user_role: RagUiRole


class RagChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: dict[str, Any]
    sources: list[dict[str, Any]]
    evaluation: dict[str, Any] | None = None


def get_rag_chat_handler() -> RagChatHandler:
    return rag_chat


@router.post(
    "/rag-chat",
    response_model=RagChatResponse,
    responses={
        401: {"model": AssistantAdminErrorResponse, "description": "Authentication required"},
        403: {
            "model": AssistantAdminErrorResponse,
            "description": "Trusted administrator required",
        },
        422: {"model": AssistantAdminErrorResponse, "description": "Invalid RAG chat request"},
        503: {"model": AssistantAdminErrorResponse, "description": "RAG chat unavailable"},
    },
    dependencies=[Depends(require_trusted_admin_origin)],
)
def rag_chat_endpoint(
    body: RagChatRequest,
    handler: Annotated[RagChatHandler, Depends(get_rag_chat_handler)],
) -> RagChatResponse:
    try:
        result = handler(query=body.message, user_role=body.user_role)
        return RagChatResponse.model_validate(result)
    except Exception as exc:
        logger.warning(
            "administrator_rag_chat_failed",
            extra={"failure_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "rag_chat_unavailable",
                "message": "The RAG chat request could not be completed.",
            },
        ) from exc
