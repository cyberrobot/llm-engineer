import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from core.config import AUDIT_LOG_LIMIT, DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from main import app
from shared.dependencies.rate_limit import limiter

OVERSIZED_LIMIT = 999999999999999999999999999999


def _require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("LEGACY_RAG_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for legacy RAG PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("LEGACY_RAG_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


@pytest.fixture
def persisted_audit_questions() -> Iterator[list[str]]:
    _require_database()
    init_db()
    marker = f"legacy-limit-{uuid4().hex}"
    inserted_ids: list[int] = []
    questions = [f"{marker}-{index:02d}" for index in range(AUDIT_LOG_LIMIT + 2)]

    try:
        with get_connection() as connection:
            for question in questions:
                inserted = connection.execute(
                    """
                    INSERT INTO audit_logs (
                        timestamp,
                        user_role,
                        question,
                        queries,
                        reply,
                        retrieved_chunks,
                        reranked_chunks,
                        evaluation,
                        metrics
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
                        "manager",
                        question,
                        json.dumps([question]),
                        json.dumps({"answer": "Characterized answer", "source_ids": []}),
                        json.dumps([]),
                        json.dumps([]),
                        json.dumps({}),
                        json.dumps({"cache_hit": False}),
                    ),
                ).fetchone()
                assert inserted is not None
                inserted_ids.append(inserted[0])
        yield list(reversed(questions))
    finally:
        if inserted_ids:
            with get_connection() as connection:
                connection.execute("DELETE FROM audit_logs WHERE id = ANY(%s)", (inserted_ids,))


@pytest.fixture
def postgres_client() -> Iterator[TestClient]:
    previous = limiter.enabled
    limiter.enabled = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        limiter.enabled = previous


@pytest.mark.parametrize(
    ("query", "expected_count"),
    [
        ("", AUDIT_LOG_LIMIT),
        ("?limit=4", 4),
        ("?limit=0", 0),
        ("?limit=4&limit=7", 7),
    ],
    ids=["default", "explicit", "zero", "repeated-last-wins"],
)
def test_audit_limits_execute_through_postgres(
    postgres_client: TestClient,
    persisted_audit_questions: list[str],
    query: str,
    expected_count: int,
) -> None:
    response = postgres_client.get(f"/audit-logs{query}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert [item["question"] for item in response.json()] == persisted_audit_questions[
        :expected_count
    ]


@pytest.mark.parametrize(
    "query",
    ["?limit=-2", f"?limit={OVERSIZED_LIMIT}"],
    ids=["negative", "exceeds-postgres-bigint"],
)
def test_audit_limits_rejected_by_postgres_surface_current_http_500(
    postgres_client: TestClient,
    persisted_audit_questions: list[str],
    query: str,
) -> None:
    response = postgres_client.get(f"/audit-logs{query}")

    assert response.status_code == 500
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.text == "Internal Server Error"


def test_malformed_audit_limit_is_rejected_before_postgres(
    postgres_client: TestClient,
    persisted_audit_questions: list[str],
) -> None:
    response = postgres_client.get("/audit-logs?limit=nope")

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "int_parsing",
                "loc": ["query", "limit"],
                "msg": "Input should be a valid integer, unable to parse string as an integer",
                "input": "nope",
            }
        ]
    }
