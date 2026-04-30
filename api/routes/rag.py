import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.audit import log_rag_event
from api.services.llm import ask_rag, estimate_tokens
from api.services.rerank import rerank_chunks
from api.services.retrieval import search_chunks

router = APIRouter()


class RagChatRequest(BaseModel):
    message: str
    keyword_query: str
    user_role: str = "user"


class RagChatResponse(BaseModel):
    reply: str
    sources: list[dict]


@router.post("/rag-chat", response_model=RagChatResponse)
def rag_chat(request: RagChatRequest):
    try:
        start_time = time.time()
        results = search_chunks(request.message, request.keyword_query, request.user_role, limit=3)
        retrieval_time = time.time() - start_time
        if not results:
            return RagChatResponse(
                reply="I could not find relevant information in the provided documents.", sources=[]
            )
        reranked = rerank_chunks(request.message, results)
        llm_start_time = time.time()
        reply = ask_rag(request.message, reranked)
        input_tokens = estimate_tokens(request.message)
        output_tokens = estimate_tokens(reply)
        llm_time = time.time() - llm_start_time
        total_time = time.time() - start_time

        log_rag_event(
            user_role=request.user_role,
            question=request.message,
            results=results,
            reply=reply,
            metrics={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "retrieval_time": round(retrieval_time, 4),
                "llm_time": round(llm_time, 4),
                "total_time": round(total_time, 4),
            },
        )

        sources = [
            {
                "id": chunk["id"],
                "text": chunk["text"][:150],
                "distance": chunk["distance"],
                "keyword_match": chunk["keyword_match"],
                "hybrid_score": chunk["hybrid_score"],
            }
            for chunk in results
        ]

        return RagChatResponse(reply=reply, sources=sources)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
