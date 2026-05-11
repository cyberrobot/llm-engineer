import time

from fastapi import HTTPException

from api.services.audit import get_latest_audit_log_for_query, log_rag_event
from api.services.cache import get_cache, set_cache
from api.services.llm import ask_rag, estimate_tokens
from api.services.rag_search import rag_search
from api.services.rerank import rerank_chunks
from api.services.retrieval import filter_chunks_by_source_ids
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
                "reply": {
                    "answer": "I could not find relevant information in the provided documents.",
                    "source_ids": [],
                },
                "sources": [],
                "debug": {},
            }
        llm_start_time = time.time()
        reranked = rerank_chunks(query, results, top_k=CHUNK_TOP_K)
        reply = ask_rag(query, reranked)
        cited_chunks = filter_chunks_by_source_ids(reranked, reply["source_ids"])
        formatted_reply = f"{reply['answer']} Sources: {', '.join(reply['source_ids'])}"
        input_tokens = estimate_tokens(query)
        output_tokens = estimate_tokens(formatted_reply)
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
            for chunk in cited_chunks
        ]

        logs = get_latest_audit_log_for_query(query, user_role)

        cached_response = {"reply": reply, "sources": sources, "debug": logs}

        set_cache(query, user_role, cached_response)

        return {"reply": reply, "sources": sources, "debug": logs}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
