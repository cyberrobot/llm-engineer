import os
import time

from fastapi import HTTPException

from api.services.audit import log_rag_event
from api.services.cache import get_cache, set_cache
from api.services.llm import ask_rag, estimate_tokens
from api.services.rag_search import rag_search
from api.services.rerank import rerank_chunks
from api.services.retrieval import filter_chunks_by_source_ids
from api.services.settings import CHUNK_TOP_K

DISABLE_CACHE = os.getenv("DISABLE_CACHE", "false").lower() == "true"
DEBUG_DELAY = os.getenv("DEBUG_DELAY", "false").lower() == "true"


def rag_chat(query: str, user_role: str):
    if DEBUG_DELAY:
        time.sleep(2)
    try:
        start_time = time.perf_counter()
        cached = get_cache(query, user_role)
        if cached and not DISABLE_CACHE:
            log_rag_event(
                user_role=user_role,
                question=query,
                retrieved_chunks=cached["debug"]["retrieved_chunks"],
                queries=cached["debug"]["queries"],
                reply=cached["debug"]["reply"],
                metrics={
                    **cached["debug"]["metrics"],
                    "cache_hit": True,
                    "retrieval_time": 0,
                    "llm_time": 0,
                    "total_time": round((time.perf_counter() - start_time) * 1000, 4),
                },
            )
            return cached

        rag_search_output = rag_search(query, user_role)
        results = rag_search_output["results"]
        multi_query = rag_search_output["multi_query"]
        retrieval_time = (time.perf_counter() - start_time) * 1000
        if not results:
            return {
                "reply": {
                    "answer": "I could not find relevant information in the provided documents.",
                    "source_ids": [],
                },
                "sources": [],
                "debug": {},
            }
        llm_start_time = time.perf_counter()
        reranked = rerank_chunks(query, results, top_k=CHUNK_TOP_K)
        reply = ask_rag(query, reranked)
        cited_chunks = filter_chunks_by_source_ids(reranked, reply["source_ids"])
        formatted_reply = f"{reply['answer']} Sources: {', '.join(reply['source_ids'])}"
        input_tokens = estimate_tokens(query)
        output_tokens = estimate_tokens(formatted_reply)
        llm_time = (time.perf_counter() - llm_start_time) * 1000
        total_time = (time.perf_counter() - start_time) * 1000

        log_rag_event(
            user_role=user_role,
            question=query,
            retrieved_chunks=[
                {
                    "id": chunk["id"],
                    "doc_id": chunk["doc_id"],
                    "text_snippet": chunk["text"][:150],
                    "distance": chunk["distance"],
                    "keyword_match": chunk["keyword_match"],
                    "hybrid_score": chunk["hybrid_score"],
                    "rank": rank,
                }
                for rank, chunk in enumerate(reranked, start=1)
            ],
            queries=multi_query,
            reply=reply,
            metrics={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "retrieval_time": round(retrieval_time, 4),
                "llm_time": round(llm_time, 4),
                "total_time": round(total_time, 4),
                "cache_hit": False,
            },
        )

        sources = [
            {
                "id": chunk["id"],
                "text": chunk["text"][:150],
            }
            for chunk in cited_chunks
        ]
        cached_response = {"reply": reply, "sources": sources}

        set_cache(query, user_role, cached_response)

        return cached_response

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
