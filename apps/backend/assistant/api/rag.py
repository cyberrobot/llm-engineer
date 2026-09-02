import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from assistant.api.rag_ui_security import (
    RagRetrievalAuthorization,
    require_rag_retrieval_authorization,
    resolve_effective_rag_role,
)
from assistant.application.rag_chat import rag_chat
from assistant.schemas.chat import MAX_CHAT_MESSAGE_LENGTH
from shared.dependencies.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_RAG_MESSAGE_CHARACTERS = MAX_CHAT_MESSAGE_LENGTH


class RagChatRequest(BaseModel):
    message: str = Field(max_length=MAX_RAG_MESSAGE_CHARACTERS)
    user_role: str | None = None


class RagChatResponse(BaseModel):
    reply: dict
    sources: list[dict]
    evaluation: dict | None = None


@router.post("/rag-chat", response_model=RagChatResponse)
@limiter.limit("20/minute")
def rag_chat_endpoint(
    request: Request,
    response: Response,
    body: RagChatRequest,
    authorization: Annotated[
        RagRetrievalAuthorization, Depends(require_rag_retrieval_authorization)
    ],
):
    del request
    response.headers["Cache-Control"] = "no-store"
    effective_role = resolve_effective_rag_role(body.user_role, authorization)
    try:
        return rag_chat(query=body.message, user_role=effective_role)
    except HTTPException as exc:
        if exc.status_code >= 500:
            logger.error(
                "rag_ui_chat_failed",
                extra={
                    "administrator_id": authorization.principal_id,
                    "error_type": type(exc.__cause__ or exc).__name__,
                },
            )
        detail = "Internal server error" if exc.status_code >= 500 else exc.detail
        headers = dict(exc.headers or {})
        headers["Cache-Control"] = "no-store"
        raise HTTPException(
            status_code=exc.status_code,
            detail=detail,
            headers=headers,
        ) from exc
    except Exception as exc:
        logger.error(
            "rag_ui_chat_failed",
            extra={
                "administrator_id": authorization.principal_id,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
            headers={"Cache-Control": "no-store"},
        ) from exc
