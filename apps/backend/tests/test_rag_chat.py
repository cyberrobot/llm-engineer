from unittest.mock import patch

import pytest
from fastapi import HTTPException

from assistant.application import rag_chat


def chunk(chunk_id="chunk-1", text="chunk text", source_id=None):
    return {
        "id": source_id or chunk_id,
        "doc_id": "doc-1",
        "text": text,
        "distance": 0.2,
        "keyword_match": True,
        "hybrid_score": 0.8,
    }


def test_format_chunks_for_audit_adds_rank_and_snippet():
    long_text = "a" * 160

    result = rag_chat.format_chunks_for_audit([chunk(text=long_text)])

    assert result == [
        {
            "id": "chunk-1",
            "doc_id": "doc-1",
            "text_snippet": "a" * 150,
            "distance": 0.2,
            "keyword_match": True,
            "hybrid_score": 0.8,
            "rank": 1,
        }
    ]


def test_get_cached_response_returns_cached_value_and_logs_audit_hit():
    cached_response = {
        "reply": {"answer": "cached answer", "source_ids": ["chunk-1"]},
        "sources": [{"id": "chunk-1", "text": "source"}],
    }
    latest_debug_event = {
        "retrieved_chunks": [{"id": "retrieved"}],
        "reranked_chunks": [{"id": "reranked"}],
        "reply": cached_response["reply"],
        "queries": [{"query": "expanded"}],
        "evaluation": {"sentences": [], "metrics": {"total_sentences": 0}},
        "metrics": {"input_tokens": 3, "cache_hit": False},
    }

    with (
        patch.object(rag_chat, "DISABLE_CACHE", False),
        patch.object(rag_chat, "DISABLE_AUDIT_LOGS", False),
        patch.object(rag_chat, "get_cache", return_value=cached_response),
        patch.object(
            rag_chat,
            "get_latest_audit_log_for_query",
            return_value=latest_debug_event,
        ),
        patch.object(rag_chat, "time") as time_mock,
        patch.object(rag_chat, "log_rag_event") as log_rag_event,
    ):
        time_mock.perf_counter.return_value = 2.0
        result = rag_chat.get_cached_response("question", "user", start_time=1.0)

    assert result == cached_response
    log_rag_event.assert_called_once_with(
        user_role="user",
        question="question",
        retrieved_chunks=latest_debug_event["retrieved_chunks"],
        reranked_chunks=latest_debug_event["reranked_chunks"],
        reply=latest_debug_event["reply"],
        queries=latest_debug_event["queries"],
        evaluation=latest_debug_event["evaluation"],
        metrics={
            "input_tokens": 3,
            "cache_hit": True,
            "retrieval_time": 0,
            "llm_time": 0,
            "total_time": 1000.0,
        },
    )


def test_rag_chat_returns_cached_response_without_retrieval():
    cached_response = {
        "reply": {"answer": "cached answer", "source_ids": ["chunk-1"]},
        "sources": [{"id": "chunk-1", "text": "source"}],
    }

    with (
        patch.object(rag_chat, "DEBUG_DELAY", False),
        patch.object(rag_chat, "get_cached_response", return_value=cached_response),
        patch.object(rag_chat, "retrieve_context") as retrieve_context,
    ):
        result = rag_chat.rag_chat("question", "user")

    assert result == cached_response
    retrieve_context.assert_not_called()


def test_rag_chat_returns_empty_response_when_no_context_is_found():
    with (
        patch.object(rag_chat, "DEBUG_DELAY", False),
        patch.object(rag_chat, "get_cached_response", return_value=None),
        patch.object(rag_chat, "retrieve_context", return_value=([], [], 4.2)),
        patch.object(rag_chat, "generate_answer") as generate_answer,
        patch.object(rag_chat, "set_cache") as set_cache,
    ):
        result = rag_chat.rag_chat("question", "user")

    assert result == rag_chat.empty_response()
    generate_answer.assert_not_called()
    set_cache.assert_not_called()


def test_rag_chat_generates_logs_caches_and_returns_response():
    results = [chunk()]
    reranked = [chunk(source_id="source-1", text="cited text")]
    cited_chunks = [reranked[0]]
    multi_query = [{"query": "question"}]
    reply = {"answer": "answer", "source_ids": ["source-1"]}
    evaluation = {
        "sentences": [
            {
                "sentence": "answer",
                "supported": True,
                "source_ids": ["source-1"],
                "support_score": 1.0,
            }
        ],
        "metrics": {
            "groundedness_score": 1.0,
            "verified_sentences": 1,
            "unsupported_claims": 0,
            "total_sentences": 1,
            "citation_count": 1,
        },
    }
    audit_event = {
        "user_role": "user",
        "question": "question",
        "retrieved_chunks": [{"id": "chunk-1"}],
        "reranked_chunks": [{"id": "source-1"}],
        "reply": reply,
        "evaluation": evaluation,
        "metrics": {"cache_hit": False},
        "queries": multi_query,
    }
    sources = [{"id": "source-1", "text": "cited text"}]
    expected_response = {"reply": reply, "sources": sources, "evaluation": evaluation}

    with (
        patch.object(rag_chat, "DEBUG_DELAY", False),
        patch.object(rag_chat, "DISABLE_AUDIT_LOGS", False),
        patch.object(rag_chat, "get_cached_response", return_value=None),
        patch.object(rag_chat, "retrieve_context", return_value=(results, multi_query, 10.0)),
        patch.object(
            rag_chat,
            "generate_answer",
            return_value=(reply, reranked, cited_chunks, 20.0),
        ),
        patch.object(rag_chat, "build_evaluation", return_value=evaluation) as build_evaluation,
        patch.object(rag_chat, "build_audit_event", return_value=audit_event) as build_audit_event,
        patch.object(rag_chat, "log_rag_event") as log_rag_event,
        patch.object(rag_chat, "format_sources", return_value=sources),
        patch.object(rag_chat, "set_cache") as set_cache,
    ):
        response = rag_chat.rag_chat("question", "user")

    assert response == expected_response
    assert "debug" not in response
    build_evaluation.assert_called_once_with("answer", reranked)
    build_audit_event.assert_called_once()
    build_kwargs = build_audit_event.call_args.kwargs
    assert build_kwargs["user_role"] == "user"
    assert build_kwargs["query"] == "question"
    assert build_kwargs["results"] == results
    assert build_kwargs["reranked"] == reranked
    assert build_kwargs["multi_query"] == multi_query
    assert build_kwargs["reply"] == reply
    assert build_kwargs["evaluation"] == evaluation
    assert build_kwargs["retrieval_time"] == 10.0
    assert build_kwargs["llm_time"] == 20.0
    log_rag_event.assert_called_once_with(**audit_event)
    set_cache.assert_called_once_with("question", "user", expected_response)


def test_build_evaluation_uses_answer_text_and_chunks():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs.", "embedding": [1, 0]}]

    with patch("assistant.domain.citation_verifier.get_embedding", return_value=[1, 0]):
        result = rag_chat.build_evaluation("Staff must wear surgical scrubs.", chunks)

    assert result == {
        "sentences": [
            {
                "sentence": "Staff must wear surgical scrubs.",
                "supported": True,
                "source_ids": ["chunk-1"],
                "support_score": 1.0,
            }
        ],
        "metrics": {
            "groundedness_score": 1.0,
            "verified_sentences": 1,
            "unsupported_claims": 0,
            "total_sentences": 1,
            "citation_count": 1,
        },
    }


def test_build_evaluation_returns_empty_results_without_answer_text():
    chunks = [{"id": "chunk-1", "text": "Staff must wear surgical scrubs."}]

    result = rag_chat.build_evaluation(" \n\t ", chunks)

    assert result == {
        "sentences": [],
        "metrics": {
            "groundedness_score": 0,
            "verified_sentences": 0,
            "unsupported_claims": 0,
            "total_sentences": 0,
            "citation_count": 0,
        },
    }


def test_build_audit_event_formats_metrics():
    reply = {"answer": "answer", "source_ids": ["source-1"]}
    evaluation = {
        "sentences": [],
        "metrics": {
            "groundedness_score": 0,
            "verified_sentences": 0,
            "unsupported_claims": 0,
            "total_sentences": 0,
            "citation_count": 0,
        },
    }

    with patch.object(rag_chat, "estimate_tokens", side_effect=[2, 5]):
        result = rag_chat.build_audit_event(
            user_role="user",
            query="question",
            results=[chunk()],
            reranked=[chunk(source_id="source-1")],
            multi_query=[{"query": "question"}],
            reply=reply,
            evaluation=evaluation,
            retrieval_time=1.23456,
            llm_time=2.34567,
            total_time=3.45678,
        )

    assert result["user_role"] == "user"
    assert result["question"] == "question"
    assert result["reply"] == reply
    assert result["evaluation"] == evaluation
    assert result["metrics"]["input_tokens"] == 2
    assert result["metrics"]["output_tokens"] == 5
    assert result["metrics"]["retrieval_time"] == 1.2346
    assert result["metrics"]["llm_time"] == 2.3457
    assert result["metrics"]["total_time"] == 3.4568
    assert result["metrics"]["cache_hit"] is False


def test_rag_chat_wraps_unexpected_errors_as_http_500():
    with (
        patch.object(rag_chat, "DEBUG_DELAY", False),
        patch.object(rag_chat, "get_cached_response", side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HTTPException) as context:
            rag_chat.rag_chat("question", "user")

    assert context.value.status_code == 500
    assert context.value.detail == "boom"
