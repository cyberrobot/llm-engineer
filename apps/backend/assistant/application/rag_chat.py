import time
from typing import Optional

from fastapi import HTTPException

from assistant.application.rag_search import rag_search
from assistant.application.retrieval import filter_chunks_by_source_ids
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.evaluation import calculate_evaluation_metrics, evaluate_answer
from assistant.infrastructure.audit import get_latest_audit_log_for_query, log_rag_event
from assistant.infrastructure.llm import ask_rag, estimate_tokens
from assistant.infrastructure.rerank import rerank_chunks
from core.config import CHUNK_TOP_K, DEBUG_DELAY, DISABLE_AUDIT_LOGS, DISABLE_CACHE
from infrastructure.cache.client import get_cache, set_cache


def format_chunks_for_audit(chunks: list[dict]) -> list[dict]:
    return [
        {
            "id": chunk["id"],
            "doc_id": chunk["doc_id"],
            "text_snippet": chunk["text"][:150],
            "distance": chunk["distance"],
            "keyword_match": chunk["keyword_match"],
            "hybrid_score": chunk["hybrid_score"],
            "rank": rank,
        }
        for rank, chunk in enumerate(chunks, start=1)
    ]


def get_cached_response(query: str, user_role: str, start_time: float) -> Optional[dict]:
    cached = get_cache(query, user_role)
    if not cached or DISABLE_CACHE:
        return None

    latest_debug_event = get_latest_audit_log_for_query(question=query, user_role=user_role)
    if latest_debug_event and not DISABLE_AUDIT_LOGS:
        log_rag_event(
            user_role=user_role,
            question=query,
            retrieved_chunks=latest_debug_event["retrieved_chunks"],
            reranked_chunks=latest_debug_event["reranked_chunks"],
            reply=latest_debug_event["reply"],
            queries=latest_debug_event["queries"],
            evaluation=latest_debug_event.get("evaluation"),
            metrics={
                **latest_debug_event["metrics"],
                "cache_hit": True,
                "retrieval_time": 0,
                "llm_time": 0,
                "total_time": round((time.perf_counter() - start_time) * 1000, 4),
            },
        )

    return cached


def retrieve_context(
    query: str, user_role: str, start_time: float
) -> tuple[list[dict], list[dict], float]:
    rag_search_output = rag_search(REDMOOR_ASSISTANT_ID, query, user_role)
    retrieval_time = (time.perf_counter() - start_time) * 1000

    return (
        rag_search_output["results"],
        rag_search_output["multi_query"],
        retrieval_time,
    )


def generate_answer(query: str, results: list[dict]) -> tuple[dict, list[dict], list[dict], float]:
    llm_start_time = time.perf_counter()
    reranked = rerank_chunks(query, results, top_k=CHUNK_TOP_K)
    reply = ask_rag(query, reranked)
    cited_chunks = filter_chunks_by_source_ids(reranked, reply["source_ids"])
    llm_time = (time.perf_counter() - llm_start_time) * 1000

    return reply, reranked, cited_chunks, llm_time


def build_evaluation(answer: str | None, chunks: list[dict]) -> dict:
    answer_text = answer or ""
    sentence_results = evaluate_answer(answer_text, chunks) if answer_text.strip() else []

    return {
        "sentences": sentence_results,
        "metrics": calculate_evaluation_metrics(sentence_results),
    }


def build_audit_event(
    *,
    user_role: str,
    query: str,
    results: list[dict],
    reranked: list[dict],
    multi_query: list[dict],
    reply: dict,
    evaluation: dict,
    retrieval_time: float,
    llm_time: float,
    total_time: float,
) -> dict:
    formatted_reply = f"{reply['answer']} Sources: {', '.join(reply['source_ids'])}"

    return {
        "user_role": user_role,
        "question": query,
        "retrieved_chunks": format_chunks_for_audit(results),
        "reranked_chunks": format_chunks_for_audit(reranked),
        "queries": multi_query,
        "reply": reply,
        "evaluation": evaluation,
        "metrics": {
            "input_tokens": estimate_tokens(query),
            "output_tokens": estimate_tokens(formatted_reply),
            "retrieval_time": round(retrieval_time, 4),
            "llm_time": round(llm_time, 4),
            "total_time": round(total_time, 4),
            "cache_hit": False,
        },
    }


def format_sources(cited_chunks: list[dict]) -> list[dict]:
    return [
        {
            "id": chunk["id"],
            "text": chunk["text"][:150],
        }
        for chunk in cited_chunks
    ]


def empty_response() -> dict:
    return {
        "reply": {
            "answer": "I could not find relevant information in the provided documents.",
            "source_ids": [],
        },
        "sources": [],
        "evaluation": build_evaluation("", []),
    }


def rag_chat(query: str, user_role: str):
    if DEBUG_DELAY:
        time.sleep(2)
    try:
        start_time = time.perf_counter()
        cached_response = get_cached_response(query, user_role, start_time)
        if cached_response:
            return cached_response

        results, multi_query, retrieval_time = retrieve_context(query, user_role, start_time)
        if not results:
            return empty_response()

        reply, reranked, cited_chunks, llm_time = generate_answer(query, results)
        evaluation = build_evaluation(reply.get("answer", ""), reranked)

        if not DISABLE_AUDIT_LOGS:
            total_time = (time.perf_counter() - start_time) * 1000
            audit_event = build_audit_event(
                user_role=user_role,
                query=query,
                results=results,
                reranked=reranked,
                multi_query=multi_query,
                reply=reply,
                evaluation=evaluation,
                retrieval_time=retrieval_time,
                llm_time=llm_time,
                total_time=total_time,
            )
            log_rag_event(**audit_event)

        sources = format_sources(cited_chunks)
        cached_response = {"reply": reply, "sources": sources, "evaluation": evaluation}

        set_cache(query, user_role, cached_response)

        return cached_response

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
