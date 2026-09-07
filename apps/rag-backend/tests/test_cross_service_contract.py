import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).parents[1]))

import infrastructure
import migrations

ROOT = Path(__file__).parents[3]


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    if os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true":
        pytest.fail("DATABASE_URL is required for the cross-service contract test")
    pytest.skip("DATABASE_URL is not configured")


def _set_backend_maintenance(database_url: str, enabled: bool) -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from datetime import datetime,timezone; "
                "from operations.domain.administration import MaintenanceState; "
                "from operations.infrastructure.runtime import PostgresRuntimeStateStore; "
                f"PostgresRuntimeStateStore().set_maintenance(MaintenanceState({enabled!r},None,datetime.now(timezone.utc),'contract-test'))"
            ),
        ],
        cwd=ROOT / "apps/backend",
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )


def test_real_backend_schema_supports_least_privilege_rag_runtime(monkeypatch):
    database_url = _database_url()
    with psycopg.connect(database_url) as connection:
        if connection.execute("SELECT to_regnamespace('rag')").fetchone()[0]:
            if os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true":
                pytest.fail("Cross-service test requires a clean disposable database")
            pytest.skip("rag schema already exists; refusing destructive test setup")
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from infrastructure.database.connection import init_db; init_db()",
        ],
        cwd=ROOT / "apps/backend",
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )
    assert migrations.upgrade(database_url) == ["20260907_001_create_rag_audit_logs"]

    reader_sql = (
        ROOT / "apps/backend/infrastructure/database/rag_read_role.sql"
    ).read_text()
    auth_sql = (ROOT / "apps/rag-backend/auth_audit_role.sql").read_text()
    assistant_id = uuid4()
    document_id = f"cross-service-document-{uuid4()}"
    chunk_id = f"cross-service-chunk-{uuid4()}"
    reader_login = f"rag_reader_test_{uuid4().hex}"
    auth_login = f"rag_auth_test_{uuid4().hex}"
    login_password = uuid4().hex
    embedding = [1.0, 0.0] + [0.0] * 1534
    with psycopg.connect(database_url) as connection:
        connection.execute(reader_sql)
        connection.execute(auth_sql)
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(reader_login), sql.Literal(login_password)
            )
        )
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(auth_login), sql.Literal(login_password)
            )
        )
        connection.execute(
            sql.SQL("GRANT rag_reader TO {}").format(sql.Identifier(reader_login))
        )
        connection.execute(
            sql.SQL("GRANT rag_auth_audit TO {}").format(sql.Identifier(auth_login))
        )
        legacy_audit_count = connection.execute(
            "SELECT count(*) FROM public.audit_logs"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO assistants (id,slug,name,status,visibility)
            VALUES (%s,%s,%s,'active','private')""",
            (assistant_id, f"cross-{assistant_id.hex}", "Cross-service test"),
        )
        connection.execute(
            """INSERT INTO documents
            (id,doc_type,access_roles,assistant_id,retrieval_state)
            VALUES (%s,'text','[]'::jsonb,%s,'enabled')""",
            (document_id, assistant_id),
        )
        connection.execute(
            """INSERT INTO chunks
            (id,doc_id,text,embedding,access_roles,assistant_id)
            VALUES (%s,%s,'operational ownership',%s,%s,%s)""",
            (chunk_id, document_id, embedding, Jsonb(["doctor"]), assistant_id),
        )

    connection_parameters = conninfo_to_dict(database_url)
    reader_url = make_conninfo(
        **{**connection_parameters, "user": reader_login, "password": login_password}
    )
    auth_url = make_conninfo(
        **{**connection_parameters, "user": auth_login, "password": login_password}
    )

    @contextmanager
    def reader_connection(*_args, **_kwargs):
        with psycopg.connect(reader_url) as connection:
            yield connection

    @contextmanager
    def auth_connection(*_args, **_kwargs):
        with psycopg.connect(auth_url) as connection:
            yield connection

    monkeypatch.setattr(infrastructure, "knowledge_connection", reader_connection)
    monkeypatch.setattr(infrastructure, "auth_audit_connection", auth_connection)

    rows = infrastructure.PostgresKnowledgeRepository().search(
        assistant_id=str(assistant_id),
        query_embedding=embedding,
        query="operational ownership",
        role="doctor",
        limit=8,
    )
    assert [row["id"] for row in rows] == [chunk_id]

    audit = infrastructure.AuditRepository()
    audit.write(
        role="doctor",
        question="ownership?",
        reply={"answer": "separate", "source_ids": [chunk_id]},
        retrieved=[],
        reranked=[],
        queries=["ownership?"],
        evaluation={},
        metrics={},
    )
    assert audit.list(1)[0]["question"] == "ownership?"
    assert infrastructure.MaintenanceRepository().is_enabled() is False
    _set_backend_maintenance(database_url, True)
    assert infrastructure.MaintenanceRepository().is_enabled() is True
    _set_backend_maintenance(database_url, False)
    assert infrastructure.MaintenanceRepository().is_enabled() is False

    for connection_factory, statement in (
        (reader_connection, "UPDATE documents SET retrieval_state='disabled'"),
        (reader_connection, "CREATE TABLE reader_forbidden(id integer)"),
        (auth_connection, "SELECT id FROM documents"),
        (
            auth_connection,
            "UPDATE operations_runtime_state SET maintenance_enabled=TRUE",
        ),
        (auth_connection, "CREATE TABLE rag.auth_forbidden(id integer)"),
    ):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            connection_factory() as connection,
        ):
            connection.execute(statement)

    with psycopg.connect(database_url) as connection:
        assert (
            connection.execute("SELECT count(*) FROM public.audit_logs").fetchone()[0]
            == legacy_audit_count
        )
        connection.execute("DELETE FROM chunks WHERE id=%s", (chunk_id,))
        connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        connection.execute("DELETE FROM assistants WHERE id=%s", (str(assistant_id),))
        connection.execute("DROP SCHEMA rag CASCADE")
        connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(reader_login)))
        connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(auth_login)))
