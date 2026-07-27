import json
from datetime import datetime, timezone
from unittest.mock import patch

from api.db import database
from api.services import audit


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.execute_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor


def test_log_rag_event_inserts_evaluation_column():
    cursor = FakeCursor()
    evaluation = {
        "sentences": [
            {
                "sentence": "Staff must wear surgical scrubs.",
                "supported": True,
                "source_ids": ["chunk-1"],
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

    with patch.object(audit, "get_connection", return_value=FakeConnection(cursor)):
        audit.log_rag_event(
            user_role="user",
            question="question",
            retrieved_chunks=[{"id": "retrieved"}],
            reranked_chunks=[{"id": "reranked"}],
            reply={"answer": "answer", "source_ids": ["chunk-1"]},
            metrics={"cache_hit": False},
            queries=[{"query": "question"}],
            evaluation=evaluation,
        )

    query, params = cursor.execute_calls[0]

    assert "evaluation" in query
    assert json.loads(params[7]) == evaluation
    assert json.loads(params[8]) == {"cache_hit": False}


def test_get_audit_logs_returns_evaluation():
    timestamp = datetime(2026, 6, 12, tzinfo=timezone.utc)
    evaluation = {"sentences": [], "metrics": {"total_sentences": 0}}
    cursor = FakeCursor(
        rows=[
            (
                1,
                timestamp,
                "user",
                "question",
                {"answer": "answer", "source_ids": []},
                [{"id": "retrieved"}],
                [{"id": "reranked"}],
                {"cache_hit": False},
                [{"query": "question"}],
                evaluation,
            )
        ]
    )

    with patch.object(audit, "get_connection", return_value=FakeConnection(cursor)):
        result = audit.get_audit_logs(limit=10)

    query, params = cursor.execute_calls[0]

    assert "evaluation" in query
    assert params == (10,)
    assert result == [
        {
            "id": 1,
            "timestamp": timestamp.isoformat(),
            "user_role": "user",
            "question": "question",
            "reply": {"answer": "answer", "source_ids": []},
            "retrieved_chunks": [{"id": "retrieved"}],
            "reranked_chunks": [{"id": "reranked"}],
            "metrics": {"cache_hit": False},
            "queries": [{"query": "question"}],
            "evaluation": evaluation,
        }
    ]


def test_init_db_adds_evaluation_column_if_missing():
    cursor = FakeCursor()

    with patch.object(database, "get_connection", return_value=FakeConnection(cursor)):
        database.init_db()

    queries = [query for query, _params in cursor.execute_calls]

    assert any(
        "ALTER TABLE audit_logs" in query
        and "ADD COLUMN IF NOT EXISTS evaluation" in query
        for query in queries
    )


def test_init_db_adds_upload_schema():
    cursor = FakeCursor()

    with patch.object(database, "get_connection", return_value=FakeConnection(cursor)):
        database.init_db()

    queries = [query for query, _params in cursor.execute_calls]

    assert any("CREATE TABLE IF NOT EXISTS ingestion_jobs" in query for query in queries)
    assert any(
        "ALTER TABLE documents" in query and "ADD COLUMN IF NOT EXISTS status" in query
        for query in queries
    )
    assert any(
        "ALTER TABLE documents" in query and "ADD COLUMN IF NOT EXISTS upload_path" in query
        for query in queries
    )
    assert any(
        "ALTER TABLE documents" in query and "ADD COLUMN IF NOT EXISTS original_filename" in query
        for query in queries
    )
