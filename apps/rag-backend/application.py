import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pysbd  # type: ignore[import-untyped]
from config import settings
from domain import REDMOOR_ASSISTANT_ID, RequestTimedOut

PROMPTS = Path(__file__).resolve().parent / "prompts"
query_cache: dict[str, list[str]] = {}
MAX_QUERY_CACHE_SIZE = 100
sentence_segmenter = pysbd.Segmenter(language="en", clean=False)


@dataclass(frozen=True)
class RagChatOutcome:
    response: dict
    audit_event: dict | None
    cache_response: dict | None


def _ensure_before_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise RequestTimedOut


class KnowledgeRepository(Protocol):
    def search(self, *, deadline: float | None = None, **kwargs) -> list[dict]: ...


class RagProvider(Protocol):
    def embedding(self, text: str, *, deadline: float | None = None) -> list[float]: ...
    def text(self, prompt: str, *, deadline: float | None = None) -> str: ...


class RagCache(Protocol):
    def get(
        self, query: str, role: str, *, deadline: float | None = None
    ) -> dict | None: ...
    def set(
        self,
        query: str,
        role: str,
        value: dict,
        *,
        deadline: float | None = None,
    ) -> None: ...


class RagAuditRepository(Protocol):
    def latest(
        self, *, question: str, role: str, deadline: float | None = None
    ) -> dict | None: ...
    def write(self, *, deadline: float | None = None, **kwargs) -> None: ...


def prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def build_query_generation_prompt(query: str) -> str:
    return f"\n{prompt('query_generation.md')}\n\nUser query: \n{query}\n"


def build_rerank_prompt(query: str, chunks: list[dict]) -> str:
    chunk_lines = "\n".join(
        f"[{index}] {chunk['text']}" for index, chunk in enumerate(chunks)
    )
    return f"""
{prompt("rerank_chunks.md")}

Query:
{query}

Chunks:
{chunk_lines}
"""


def build_answer_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[Source: {chunk['id']}]\n{chunk['text']}" for chunk in chunks
    )
    return (
        f"\n{prompt('answer_system.md')}\n\nContext:\n{context}"
        f"\n\nQuestion: \n{question}\n"
    )


def empty_response() -> dict:
    return {
        "reply": {
            "answer": "I could not find relevant information in the provided documents.",
            "source_ids": [],
        },
        "sources": [],
        "evaluation": {
            "sentences": [],
            "metrics": {
                "groundedness_score": 0,
                "verified_sentences": 0,
                "unsupported_claims": 0,
                "total_sentences": 0,
                "citation_count": 0,
            },
        },
    }


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(
        sum(x * x for x in right)
    )
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def evaluate_answer(
    answer: str,
    chunks: list[dict],
    provider: RagProvider,
    deadline: float | None = None,
) -> dict:
    normalised = " ".join(answer.split())
    sentences = [
        sentence.strip()
        for sentence in sentence_segmenter.segment(normalised)
        if sentence.strip()
    ]
    results = []
    for sentence in sentences:
        sentence_embedding = provider.embedding(sentence, deadline=deadline)
        supported_source_ids: list[str] = []
        best_score = 0.0
        for chunk in chunks:
            chunk_embedding = chunk.get("embedding") or provider.embedding(
                chunk.get("text", ""), deadline=deadline
            )
            score = _cosine(sentence_embedding, chunk_embedding)
            best_score = max(best_score, score)
            if score >= 0.78:
                supported_source_ids.append(str(chunk["id"]))
        results.append(
            {
                "sentence": sentence,
                "supported": bool(supported_source_ids),
                "source_ids": supported_source_ids,
                "support_score": round(best_score, 4),
            }
        )
    supported = [item for item in results if item["supported"]]
    cited_source_ids = {
        source_id for item in supported for source_id in item["source_ids"]
    }
    return {
        "sentences": results,
        "metrics": {
            "groundedness_score": round(len(supported) / len(results), 2)
            if results
            else 0,
            "verified_sentences": len(supported),
            "unsupported_claims": len(results) - len(supported),
            "total_sentences": len(results),
            "citation_count": len(cited_source_ids),
        },
    }


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
        for rank, chunk in enumerate(chunks, 1)
    ]


def prepare_rag_chat(
    query: str,
    role: str,
    repository: KnowledgeRepository,
    provider: RagProvider,
    cache: RagCache,
    audit: RagAuditRepository,
    deadline: float | None = None,
) -> RagChatOutcome:
    start = time.perf_counter()
    cached = cache.get(query, role, deadline=deadline)
    if cached:
        _ensure_before_deadline(deadline)
        latest = (
            audit.latest(question=query, role=role, deadline=deadline)
            if not settings.disable_audit
            else None
        )
        audit_event = None
        if latest is not None:
            _ensure_before_deadline(deadline)
            audit_event = {
                "role": role,
                "question": query,
                "reply": latest["reply"],
                "retrieved": latest["retrieved_chunks"],
                "reranked": latest["reranked_chunks"],
                "queries": latest["queries"],
                "evaluation": latest["evaluation"],
                "metrics": {
                    **latest["metrics"],
                    "cache_hit": True,
                    "retrieval_time": 0,
                    "llm_time": 0,
                    "total_time": round((time.perf_counter() - start) * 1000, 4),
                },
            }
        cached.setdefault("evaluation", empty_response()["evaluation"])
        return RagChatOutcome(cached, audit_event, None)
    queries: Any = [query]
    if query in query_cache:
        queries = query_cache[query]
    else:
        try:
            generated = json.loads(
                provider.text(build_query_generation_prompt(query), deadline=deadline)
            )
            queries = generated
        except (json.JSONDecodeError, ValueError):
            queries = [query]
        if len(query_cache) > MAX_QUERY_CACHE_SIZE:
            query_cache.pop(next(iter(query_cache)))
        query_cache[query] = queries
    results: list[dict[str, Any]] = []
    for item in queries:
        query_results = repository.search(
            assistant_id=REDMOOR_ASSISTANT_ID,
            query_embedding=provider.embedding(item, deadline=deadline),
            query=item,
            role=role,
            limit=8,
            deadline=deadline,
        )
        if query_results and query_results[0]["distance"] <= 0.8:
            results.extend(query_results)
    retrieval_time = (time.perf_counter() - start) * 1000
    unique: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in results:
        if item["id"] not in seen:
            unique.append(item)
            seen.add(item["id"])
    if not unique:
        return RagChatOutcome(empty_response(), None, None)
    llm_start = time.perf_counter()
    try:
        ranked = json.loads(
            provider.text(build_rerank_prompt(query, unique), deadline=deadline)
        )
    except Exception:  # noqa: BLE001 - preserves legacy rerank JSON fallback
        ranked = list(range(len(unique)))
    reranked = [unique[index] for index in ranked[:3]]
    answer = json.loads(
        provider.text(build_answer_prompt(query, reranked), deadline=deadline)
    )
    llm_time = (time.perf_counter() - llm_start) * 1000
    ids: set[Any] = set(answer["source_ids"])
    sources = [
        {"id": str(x["id"]), "text": x["text"][:150]}
        for x in reranked
        if str(x["id"]) in ids
    ]
    evaluation = evaluate_answer(answer["answer"], reranked, provider, deadline)
    result = {"reply": answer, "sources": sources, "evaluation": evaluation}
    _ensure_before_deadline(deadline)
    audit_event = None
    if not settings.disable_audit:
        audit_event = {
            "role": role,
            "question": query,
            "reply": answer,
            "retrieved": format_chunks_for_audit(unique),
            "reranked": format_chunks_for_audit(reranked),
            "queries": queries,
            "evaluation": evaluation,
            "metrics": {
                "input_tokens": estimate_tokens(query),
                "output_tokens": estimate_tokens(
                    f"{answer['answer']} Sources: {', '.join(answer['source_ids'])}"
                ),
                "retrieval_time": round(retrieval_time, 4),
                "llm_time": round(llm_time, 4),
                "total_time": round((time.perf_counter() - start) * 1000, 4),
                "cache_hit": False,
            },
        }
    _ensure_before_deadline(deadline)
    return RagChatOutcome(result, audit_event, result)


def commit_rag_chat_outcome(
    outcome: RagChatOutcome,
    query: str,
    role: str,
    cache: RagCache,
    audit: RagAuditRepository,
    deadline: float | None = None,
) -> dict:
    _ensure_before_deadline(deadline)
    if outcome.audit_event is not None:
        audit.write(**outcome.audit_event, deadline=deadline)
    _ensure_before_deadline(deadline)
    if outcome.cache_response is not None:
        cache.set(query, role, outcome.cache_response, deadline=deadline)
    _ensure_before_deadline(deadline)
    return outcome.response


def rag_chat(
    query: str,
    role: str,
    repository: KnowledgeRepository,
    provider: RagProvider,
    cache: RagCache,
    audit: RagAuditRepository,
    deadline: float | None = None,
) -> dict:
    outcome = prepare_rag_chat(
        query, role, repository, provider, cache, audit, deadline
    )
    return commit_rag_chat_outcome(outcome, query, role, cache, audit, deadline)
