from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.llm import ask_rag
from api.services.retrieval import search_chunks

router = APIRouter()


class RagChatRequest(BaseModel):
    message: str


class RagChatResponse(BaseModel):
    reply: str
    sources: list[str]


@router.post("/rag-chat", response_model=RagChatResponse)
def rag_chat(request: RagChatRequest):
    try:
        chunks = search_chunks(request.message)
        if not chunks:
            return RagChatResponse(
                reply="I could not find relevant information in the provided documents.", sources=[]
            )
        reply = ask_rag(request.message, chunks)

        sources = [chunk["id"] for chunk in chunks]

        return RagChatResponse(reply=reply, sources=sources)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
