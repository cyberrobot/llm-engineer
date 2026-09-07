from contextlib import contextmanager

import pytest

import infrastructure


class RecordingLogger:
    def __init__(self):
        self.events = []

    def error(self, event, *, extra):
        self.events.append((event, extra))

    def info(self, event, *, extra):
        self.events.append((event, extra))


@contextmanager
def unavailable_connection(*_args, **_kwargs):
    raise RuntimeError("sensitive database failure")
    yield


def test_retrieval_and_audit_failures_emit_separate_safe_events(monkeypatch):
    logger = RecordingLogger()
    monkeypatch.setattr(infrastructure, "logger", logger)
    monkeypatch.setattr(infrastructure, "knowledge_connection", unavailable_connection)
    monkeypatch.setattr(infrastructure, "auth_audit_connection", unavailable_connection)

    with pytest.raises(RuntimeError):
        infrastructure.PostgresKnowledgeRepository().search(
            assistant_id="assistant",
            query_embedding=[1.0],
            query="sensitive question",
            role="doctor",
            limit=1,
        )
    with pytest.raises(RuntimeError):
        infrastructure.AuditRepository().write(
            role="doctor",
            question="sensitive question",
            reply={},
            retrieved=[],
            reranked=[],
            queries=[],
            evaluation={},
            metrics={},
        )

    assert [event for event, _extra in logger.events] == [
        "retrieval_failed",
        "audit_write_failed",
    ]
    assert all("sensitive" not in repr(extra) for _event, extra in logger.events)


def test_successful_provider_operations_emit_denominator_events(monkeypatch):
    logger = RecordingLogger()

    class EmbeddingResult:
        def __init__(self):
            self.data = [type("Datum", (), {"embedding": [1.0]})()]

    class TextResult:
        output_text = " answer "

    class Embeddings:
        def create(self, **_kwargs):
            return EmbeddingResult()

    class Responses:
        def create(self, **_kwargs):
            return TextResult()

    class Client:
        embeddings = Embeddings()
        responses = Responses()

        def with_options(self, **_kwargs):
            return self

    provider = object.__new__(infrastructure.Provider)
    provider.client = Client()
    monkeypatch.setattr(infrastructure, "logger", logger)

    assert provider.embedding("sensitive embedding input") == [1.0]
    assert provider.text("sensitive prompt") == "answer"

    assert [
        (event, extra["operation"], extra["outcome"]) for event, extra in logger.events
    ] == [
        ("provider_request_completed", "embedding", "success"),
        ("provider_request_completed", "text_generation", "success"),
    ]
    assert all(extra["duration_ms"] >= 0 for _event, extra in logger.events)
    assert "sensitive" not in repr(logger.events)


@pytest.mark.parametrize(
    ("operation", "error_name", "expected_outcome", "expected_category"),
    [
        ("embedding", "APITimeoutError", "timeout", "provider_timeout"),
        ("text_generation", "ProviderError", "failure", "operation_failed"),
    ],
)
def test_failed_provider_operations_emit_outcome_and_safe_category(
    monkeypatch, operation, error_name, expected_outcome, expected_category
):
    logger = RecordingLogger()
    provider_error = type(error_name, (Exception,), {})

    class Embeddings:
        def create(self, **_kwargs):
            raise provider_error("sensitive provider payload")

    class Responses:
        def create(self, **_kwargs):
            raise provider_error("sensitive provider payload")

    class Client:
        embeddings = Embeddings()
        responses = Responses()

        def with_options(self, **_kwargs):
            return self

    provider = object.__new__(infrastructure.Provider)
    provider.client = Client()
    monkeypatch.setattr(infrastructure, "logger", logger)

    with pytest.raises(provider_error):
        if operation == "embedding":
            provider.embedding("sensitive embedding input")
        else:
            provider.text("sensitive prompt")

    assert [event for event, _extra in logger.events] == [
        "provider_request_failed",
        "provider_request_completed",
    ]
    assert logger.events[0][1]["operation"] == operation
    assert logger.events[0][1]["failure_category"] == expected_category
    completion = logger.events[1][1]
    assert completion["operation"] == operation
    assert completion["outcome"] == expected_outcome
    assert completion["failure_category"] == expected_category
    assert completion["duration_ms"] >= 0
    assert "sensitive" not in repr(logger.events)
