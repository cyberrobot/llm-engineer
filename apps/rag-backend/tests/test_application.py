import json
import sys
from pathlib import Path

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

    def text(self, _prompt):
        if self.responses:
            return self.responses.pop(0)
        return json.dumps(
            {"answer": "Review the checklist.", "source_ids": ["chunk-1"]}
        )

    def embedding(self, _text):
        return [1.0, 0.0]


class Cache:
    def __init__(self):
        self.value = None

    def get(self, *_args):
        return self.value

    def set(self, *_args):
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


def test_retrieval_discards_a_query_when_its_best_match_exceeds_maximum_distance(
    monkeypatch,
):
    monkeypatch.setattr(application, "query_cache", {"question": ["question"]})
    result = application.rag_chat(
        "question", "doctor", DistanceRepository(), Provider(), Cache(), Audit()
    )

    assert result == application.empty_response()
