from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.llm import ask_rag
from api.services.retrieval import search_chunks

router = APIRouter()


class RagChatRequest(BaseModel):
    message: str
    user_role: str = "user"


class RagChatResponse(BaseModel):
    reply: str
    sources: list[dict]


@router.post("/rag-chat", response_model=RagChatResponse)
def rag_chat(request: RagChatRequest):
    try:
        results = search_chunks(request.message, request.user_role, limit=3)
        chunks = [chunk for _, chunk in results]
        if not results:
            return RagChatResponse(
                reply="I could not find relevant information in the provided documents.", sources=[]
            )
        reply = ask_rag(request.message, chunks)

        sources = [
            {
                "id": chunk["id"],
                "score": results[0][0],
                "text": chunk["text"][:150],
            }
            for chunk in chunks
        ]

        return RagChatResponse(reply=reply, sources=sources)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
