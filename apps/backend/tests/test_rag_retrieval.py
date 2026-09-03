from uuid import uuid4

from assistant.application import retrieval


class StubRagKnowledgeRepository:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.results)


def result(*, chunk_id: str = "chunk-1", distance: float = 0.2) -> dict:
    return {
        "id": chunk_id,
        "doc_id": "document-1",
        "text": "Required knowledge",
        "distance": distance,
        "access_roles": ["doctor"],
        "keyword_match": 0.4,
        "hybrid_score": 0.72,
    }


def test_search_chunks_uses_injected_read_repository_and_preserves_result_mapping(monkeypatch):
    assistant_id = uuid4()
    embedding = [1.0, 0.0]
    repository = StubRagKnowledgeRepository([result()])
    monkeypatch.setattr(retrieval, "get_embedding", lambda query: embedding)

    matches = retrieval.search_chunks(
        assistant_id,
        "surgical checklist",
        "doctor",
        repository,
        limit=3,
        max_distance=0.8,
    )

    assert matches == [result()]
    assert repository.calls == [
        {
            "assistant_id": assistant_id,
            "query_embedding": embedding,
            "query": "surgical checklist",
            "access_role": "doctor",
            "limit": 3,
        }
    ]


def test_search_chunks_preserves_maximum_distance_cutoff(monkeypatch):
    repository = StubRagKnowledgeRepository([result(distance=0.81)])
    monkeypatch.setattr(retrieval, "get_embedding", lambda _query: [1.0, 0.0])

    assert retrieval.search_chunks(uuid4(), "query", "doctor", repository, max_distance=0.8) == []


def test_multi_query_search_preserves_generated_query_and_result_order(monkeypatch):
    repository = StubRagKnowledgeRepository([])
    calls = []
    monkeypatch.setattr(retrieval, "generate_queries_cached", lambda _query: ["first", "second"])

    def search_chunks(assistant_id, query, user_role, injected_repository):
        calls.append((assistant_id, query, user_role, injected_repository))
        return [result(chunk_id=f"chunk-{query}")]

    monkeypatch.setattr(retrieval, "search_chunks", search_chunks)
    assistant_id = uuid4()

    output = retrieval.multi_query_search(assistant_id, "original", "doctor", repository)

    assert output == {
        "results": [result(chunk_id="chunk-first"), result(chunk_id="chunk-second")],
        "multi_query": ["first", "second"],
    }
    assert calls == [
        (assistant_id, "first", "doctor", repository),
        (assistant_id, "second", "doctor", repository),
    ]
