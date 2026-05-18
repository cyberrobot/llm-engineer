from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.core.rate_limit import limiter
from api.services.rag_chat import rag_chat

router = APIRouter()


class RagChatRequest(BaseModel):
    message: str
    user_role: str = "user"


class RagChatResponse(BaseModel):
    reply: dict
    sources: list[dict]


@router.post("/rag-chat", response_model=RagChatResponse)
@limiter.limit("20/minute")
def rag_chat_endpoint(request: Request, body: RagChatRequest):
    return rag_chat(query=body.message, user_role=body.user_role)
