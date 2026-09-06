import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).parents[1]))

import infrastructure
import security


@pytest.fixture
def postgres_schema(monkeypatch):
    database_url = os.getenv("DATABASE_URL")
    required = os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true"
    if not database_url:
        if required:
            pytest.fail("DATABASE_URL is required for extracted RAG PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    schema = f"rag_backend_{uuid4().hex}"
    try:
        with psycopg.connect(database_url, connect_timeout=2) as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
            )
            connection.execute(
                """CREATE TABLE documents (
                id text PRIMARY KEY, assistant_id uuid NOT NULL,
                retrieval_state text NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE chunks (
                id text PRIMARY KEY, doc_id text NOT NULL REFERENCES documents(id),
                text text NOT NULL, text_search tsvector GENERATED ALWAYS AS
                (to_tsvector('english', text)) STORED, embedding vector(2) NOT NULL,
                access_roles jsonb NOT NULL, assistant_id uuid NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE audit_logs (
                id bigserial PRIMARY KEY, timestamp timestamptz NOT NULL,
                user_role text NOT NULL, question text NOT NULL, queries jsonb NOT NULL,
                reply jsonb NOT NULL, retrieved_chunks jsonb NOT NULL,
                reranked_chunks jsonb NOT NULL, evaluation jsonb NOT NULL,
                metrics jsonb NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE administrators (
                id uuid PRIMARY KEY, role text NOT NULL, status text NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE administrator_sessions (
                administrator_id uuid NOT NULL REFERENCES administrators(id),
                token_hash text NOT NULL, revoked_at timestamptz,
                expires_at timestamptz NOT NULL)"""
            )

        @contextmanager
        def connection_factory(*_args, **_kwargs):
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    sql.SQL("SET search_path TO {}, public").format(
                        sql.Identifier(schema)
                    )
                )
                yield connection

        monkeypatch.setattr(infrastructure, "knowledge_connection", connection_factory)
        monkeypatch.setattr(infrastructure, "auth_audit_connection", connection_factory)
        monkeypatch.setattr(security, "auth_audit_connection", connection_factory)
        yield connection_factory
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


def test_extracted_repository_enforces_assistant_role_state_and_ranking(
    postgres_schema,
):
    assistant_id = uuid4()
    other_assistant = uuid4()
    with postgres_schema() as connection:
        rows = [
            ("enabled", assistant_id, "enabled"),
            ("disabled", assistant_id, "disabled"),
            ("other", other_assistant, "enabled"),
        ]
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO documents (id, assistant_id, retrieval_state) VALUES (%s,%s,%s)",
                rows,
            )
            cursor.executemany(
                """INSERT INTO chunks
                (id,doc_id,text,embedding,access_roles,assistant_id)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                [
                    (
                        "best",
                        "enabled",
                        "surgical checklist",
                        [1.0, 0.0],
                        '["doctor"]',
                        assistant_id,
                    ),
                    (
                        "wrong-role",
                        "enabled",
                        "surgical checklist",
                        [1.0, 0.0],
                        '["manager"]',
                        assistant_id,
                    ),
                    (
                        "disabled",
                        "disabled",
                        "surgical checklist",
                        [1.0, 0.0],
                        '["doctor"]',
                        assistant_id,
                    ),
                    (
                        "other",
                        "other",
                        "surgical checklist",
                        [1.0, 0.0],
                        '["doctor"]',
                        other_assistant,
                    ),
                ],
            )

    result = infrastructure.PostgresKnowledgeRepository().search(
        assistant_id=str(assistant_id),
        query_embedding=[1.0, 0.0],
        query="surgical checklist",
        role="doctor",
        limit=8,
    )

    assert [row["id"] for row in result] == ["best"]
    assert result[0]["keyword_match"] > 0
    assert result[0]["hybrid_score"] == pytest.approx(
        (1 - result[0]["distance"]) * 0.8 + result[0]["keyword_match"] * 0.2
    )


def test_extracted_audit_repository_inserts_and_reads_newest_first(postgres_schema):
    repository = infrastructure.AuditRepository()
    for question in ("first", "second"):
        repository.write(
            role="doctor",
            question=question,
            reply={"answer": question, "source_ids": []},
            retrieved=[],
            reranked=[],
            queries=[question],
            evaluation={},
            metrics={},
        )

    rows = repository.list(2)

    assert [row["question"] for row in rows] == ["second", "first"]
    assert (
        repository.latest(question="first", role="doctor")["reply"]["answer"] == "first"
    )


@pytest.mark.parametrize(
    ("role", "status", "expires_delta", "revoked", "expected_status"),
    [
        ("administrator", "active", 60, False, None),
        ("administrator", "active", -60, False, 401),
        ("administrator", "active", 60, True, 401),
        ("administrator", "inactive", 60, False, 401),
        ("operator", "active", 60, False, 403),
    ],
)
def test_session_lookup_contract(
    postgres_schema, role, status, expires_delta, revoked, expected_status
):
    token = f"token-{uuid4()}"
    administrator_id = uuid4()
    now = datetime.now(timezone.utc)
    with postgres_schema() as connection:
        connection.execute(
            "INSERT INTO administrators (id,role,status) VALUES (%s,%s,%s)",
            (administrator_id, role, status),
        )
        connection.execute(
            """INSERT INTO administrator_sessions
            (administrator_id,token_hash,revoked_at,expires_at) VALUES (%s,%s,%s,%s)""",
            (
                administrator_id,
                sha256(token.encode()).hexdigest(),
                now if revoked else None,
                now + timedelta(seconds=expires_delta),
            ),
        )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/audit-logs",
            "headers": [(b"cookie", f"redmoor_admin_session={token}".encode())],
        }
    )

    if expected_status is None:
        assert security.require_admin(request).principal_id == str(administrator_id)
    else:
        with pytest.raises(Exception) as raised:
            security.require_admin(request)
        assert raised.value.status_code == expected_status


def test_auth_audit_role_allows_required_operations_and_denies_unrelated_access(
    postgres_schema,
):
    role_sql = (Path(__file__).parents[1] / "auth_audit_role.sql").read_text()
    with postgres_schema() as connection:
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
        scoped_sql = role_sql.replace("public.", f'"{schema}".').replace(
            "SCHEMA public", f'SCHEMA "{schema}"'
        )
        connection.execute(scoped_sql)

    def execute_as_role(statement, parameters=()):
        with postgres_schema() as connection:
            connection.execute("SET ROLE rag_auth_audit")
            return connection.execute(statement, parameters).fetchall()

    assert execute_as_role("SELECT id,role,status FROM administrators") == []
    inserted = execute_as_role(
        """INSERT INTO audit_logs
        (timestamp,user_role,question,queries,reply,retrieved_chunks,
         reranked_chunks,evaluation,metrics)
        VALUES (%s,'doctor','allowed','[]','{}','[]','[]','{}','{}') RETURNING id""",
        (datetime.now(timezone.utc),),
    )
    assert inserted[0][0] > 0
    assert execute_as_role("SELECT question FROM audit_logs") == [("allowed",)]

    for forbidden in (
        "UPDATE administrators SET status='inactive'",
        "DELETE FROM administrator_sessions",
        "SELECT id FROM documents",
        (
            "INSERT INTO documents (id,assistant_id,retrieval_state) "
            f"VALUES ('denied','{uuid4()}','enabled')"
        ),
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            execute_as_role(forbidden)
