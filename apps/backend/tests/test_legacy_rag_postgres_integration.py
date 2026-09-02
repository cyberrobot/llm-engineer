import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from admin_auth.dependencies import get_administrator_auth_service
from admin_auth.passwords import AdministratorPasswordService
from admin_auth.repository import InMemoryAdministratorAuthRepository
from admin_auth.service import AdministratorAuthenticationService
from core.config import AUDIT_LOG_LIMIT, DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from main import app
from shared.dependencies.rate_limit import limiter

OVERSIZED_LIMIT = 999999999999999999999999999999
NOW = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
PASSWORD = "correct horse battery staple"


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
    repository = InMemoryAdministratorAuthRepository()
    service = AdministratorAuthenticationService(
        repository,
        AdministratorPasswordService(),
        session_ttl_seconds=3600,
        login_max_failures=3,
        login_lockout_seconds=300,
        clock=lambda: NOW,
        token_factory=lambda: "legacy-rag-postgres-session",
    )
    service.bootstrap("admin@example.com", PASSWORD)
    login = service.login("admin@example.com", PASSWORD)
    app.dependency_overrides[get_administrator_auth_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("redmoor_admin_session", login.session_token)
    try:
        yield client
    finally:
        limiter.enabled = previous
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("query", "expected_count"),
    [
        ("", AUDIT_LOG_LIMIT),
        ("?limit=4", 4),
        ("?limit=4&limit=7", 7),
        ("?limit=200", AUDIT_LOG_LIMIT + 2),
    ],
    ids=["default", "explicit", "repeated-last-wins", "maximum"],
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
    assert response.headers["cache-control"] == "no-store"
    assert [item["question"] for item in response.json()] == persisted_audit_questions[
        :expected_count
    ]


@pytest.mark.parametrize(
    "query",
    ["?limit=0", "?limit=-2", "?limit=201", f"?limit={OVERSIZED_LIMIT}"],
    ids=["zero", "negative", "maximum-plus-one", "excessively-large"],
)
def test_invalid_audit_limits_are_rejected_before_postgres(
    postgres_client: TestClient,
    persisted_audit_questions: list[str],
    query: str,
) -> None:
    response = postgres_client.get(f"/audit-logs{query}")

    assert response.status_code == 422


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
