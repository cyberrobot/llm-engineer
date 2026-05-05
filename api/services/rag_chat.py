import time

from fastapi import HTTPException

from api.services.audit import log_rag_event
from api.services.cache import get_cache, set_cache
from api.services.llm import ask_rag, estimate_tokens
from api.services.rag_search import rag_search
from api.services.rerank import rerank_chunks
from api.services.settings import CHUNK_TOP_K


def rag_chat(query: str, user_role: str):
    try:
        cached = get_cache(query, user_role)
        if cached:
            return cached
        start_time = time.time()
        results = rag_search(query, user_role)
        retrieval_time = time.time() - start_time
        if not results:
            return {
                "reply": "I could not find relevant information in the provided documents.",
                "sources": [],
            }
        llm_start_time = time.time()
        reranked = rerank_chunks(query, results, top_k=CHUNK_TOP_K)
        reply = ask_rag(query, reranked)
        input_tokens = estimate_tokens(query)
        output_tokens = estimate_tokens(reply)
        llm_time = time.time() - llm_start_time
        total_time = time.time() - start_time

        log_rag_event(
            user_role=user_role,
            question=query,
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
            }
            for chunk in results
        ]

        cached_response = {"reply": reply, "sources": sources}

        set_cache(query, user_role, cached_response)

        return {"reply": reply, "sources": sources}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
