import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import application


class Repository:
    def search(self, **_kwargs):
        return [
            {
                "id": "chunk-1",
                "doc_id": "document-1",
                "text": "Staff must review the checklist.",
                "distance": 0.2,
                "keyword_match": 0.4,
                "hybrid_score": 0.8,
                "embedding": [1.0, 0.0],
            }
        ]


class DistanceRepository:
    def __init__(self):
        self.calls = 0

    def search(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return [
                {
                    "id": "too-far",
                    "doc_id": "document-1",
                    "text": "Irrelevant",
                    "distance": 0.81,
                    "keyword_match": 0.0,
                    "hybrid_score": 0.1,
                },
                {
                    "id": "would-have-been-kept",
                    "doc_id": "document-1",
                    "text": "Also irrelevant",
                    "distance": 0.2,
                    "keyword_match": 0.0,
                    "hybrid_score": 0.1,
                },
            ]
        return []


class Provider:
    def __init__(self):
        self.responses = [json.dumps(["checklist"]), json.dumps([0])]

    def text(self, _prompt, **_kwargs):
        if self.responses:
            return self.responses.pop(0)
        return json.dumps(
            {"answer": "Review the checklist.", "source_ids": ["chunk-1"]}
        )

    def embedding(self, _text, **_kwargs):
        return [1.0, 0.0]


class Cache:
    def __init__(self):
        self.value = None

    def get(self, *_args, **_kwargs):
        return self.value

    def set(self, *_args, **_kwargs):
        self.value = _args[-1]


class Audit:
    def __init__(self):
        self.events = []

    def write(self, **event):
        self.events.append(event)

    def latest(self, **_kwargs):
        return None


def test_rag_chat_preserves_source_and_audit_shapes(monkeypatch):
    monkeypatch.setattr(application, "query_cache", {})
    audit = Audit()
    result = application.rag_chat(
        "question", "doctor", Repository(), Provider(), Cache(), audit
    )

    assert result["reply"]["source_ids"] == ["chunk-1"]
    assert result["sources"] == [
        {"id": "chunk-1", "text": "Staff must review the checklist."}
    ]
    assert result["evaluation"]["metrics"]["groundedness_score"] == 1.0
    assert audit.events[0]["retrieved"] == [
        {
            "id": "chunk-1",
            "doc_id": "document-1",
            "text_snippet": "Staff must review the checklist.",
            "distance": 0.2,
            "keyword_match": 0.4,
            "hybrid_score": 0.8,
            "rank": 1,
        }
    ]
    assert audit.events[0]["metrics"]["cache_hit"] is False


def test_empty_response_has_frozen_legacy_shape():
    assert application.empty_response() == {
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


def test_composed_provider_prompts_match_legacy_format_exactly():
    query = "How do I review this?"
    chunks = [{"id": "chunk-1", "text": "First"}, {"id": "chunk-2", "text": "Second"}]

    assert application.build_query_generation_prompt(query) == (
        f"\n{application.prompt('query_generation.md')}\n\nUser query: \n{query}\n"
    )
    assert (
        application.build_rerank_prompt(query, chunks)
        == f"""
{application.prompt("rerank_chunks.md")}

Query:
{query}

Chunks:
[0] First
[1] Second
"""
    )
    assert application.build_answer_prompt(query, chunks) == (
        f"\n{application.prompt('answer_system.md')}\n\nContext:\n"
        f"[Source: chunk-1]\nFirst\n\n[Source: chunk-2]\nSecond"
        f"\n\nQuestion: \n{query}\n"
    )


@pytest.mark.parametrize(
    "answer",
    [
        {"answer": "Missing sources"},
        {"source_ids": ["chunk-1"]},
    ],
)
def test_malformed_answer_shape_preserves_legacy_key_error(monkeypatch, answer):
    class MalformedAnswerProvider(Provider):
        def __init__(self):
            self.responses = [
                json.dumps(["checklist"]),
                json.dumps([0]),
                json.dumps(answer),
            ]

    monkeypatch.setattr(application, "query_cache", {})

    with pytest.raises(KeyError):
        application.rag_chat(
            "question",
            "doctor",
            Repository(),
            MalformedAnswerProvider(),
            Cache(),
            Audit(),
        )


def test_retrieval_discards_a_query_when_its_best_match_exceeds_maximum_distance(
    monkeypatch,
):
    monkeypatch.setattr(application, "query_cache", {"question": ["question"]})
    result = application.rag_chat(
        "question", "doctor", DistanceRepository(), Provider(), Cache(), Audit()
    )

    assert result == application.empty_response()


def test_cache_hit_does_not_read_or_write_audit_when_auditing_is_disabled(monkeypatch):
    class CacheHit:
        def get(self, *_args, **_kwargs):
            return application.empty_response()

        def set(self, *_args, **_kwargs):
            raise AssertionError("cache hit must not be overwritten")

    class NoAudit:
        def latest(self, **_kwargs):
            raise AssertionError("disabled audit must not be read")

        def write(self, **_kwargs):
            raise AssertionError("disabled audit must not be written")

    monkeypatch.setattr(
        application, "settings", replace(application.settings, disable_audit=True)
    )

    assert (
        application.rag_chat(
            "question", "doctor", Repository(), Provider(), CacheHit(), NoAudit()
        )
        == application.empty_response()
    )


def test_expired_deadline_prevents_audit_and_cache_side_effects(monkeypatch):
    class RecordingCache(Cache):
        def __init__(self):
            super().__init__()
            self.writes = 0

        def set(self, *_args, **_kwargs):
            self.writes += 1

    class RecordingAudit(Audit):
        pass

    monkeypatch.setattr(application, "query_cache", {})
    cache = RecordingCache()
    audit = RecordingAudit()

    try:
        application.rag_chat(
            "question",
            "doctor",
            Repository(),
            Provider(),
            cache,
            audit,
            deadline=time.monotonic() - 1,
        )
    except application.RequestTimedOut:
        pass
    else:
        raise AssertionError("expected deadline to stop side effects")

    assert audit.events == []
    assert cache.writes == 0
