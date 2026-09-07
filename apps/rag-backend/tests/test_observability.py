from contextlib import contextmanager

import pytest

import infrastructure


class RecordingLogger:
    def __init__(self):
        self.events = []

    def error(self, event, *, extra):
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


def test_provider_timeout_identifies_operation_without_logging_input(monkeypatch):
    logger = RecordingLogger()
    timeout_error = type("APITimeoutError", (Exception,), {})

    class Embeddings:
        def create(self, **_kwargs):
            raise timeout_error("sensitive provider payload")

    class Client:
        embeddings = Embeddings()

        def with_options(self, **_kwargs):
            return self

    provider = object.__new__(infrastructure.Provider)
    provider.client = Client()
    monkeypatch.setattr(infrastructure, "logger", logger)

    with pytest.raises(timeout_error):
        provider.embedding("sensitive embedding input")

    assert logger.events == [
        (
            "provider_request_failed",
            {
                "operation": "embedding",
                "failure_category": "provider_timeout",
                "duration_ms": logger.events[0][1]["duration_ms"],
            },
        )
    ]
    assert "sensitive" not in repr(logger.events)
