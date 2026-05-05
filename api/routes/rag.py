from fastapi import APIRouter
from pydantic import BaseModel

from api.services.rag_chat import rag_chat

router = APIRouter()


class RagChatRequest(BaseModel):
    message: str
    user_role: str = "user"


class RagChatResponse(BaseModel):
    reply: str
    sources: list[dict]


@router.post("/rag-chat", response_model=RagChatResponse)
def rag_chat_endpoint(request: RagChatRequest):
    return rag_chat(query=request.message, user_role=request.user_role)
