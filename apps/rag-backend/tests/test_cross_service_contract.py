import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).parents[1]))

import infrastructure
import main as rag_main
import migrations

ROOT = Path(__file__).parents[3]
BACKEND_HTTP_PROBE = Path(__file__).with_name("backend_http_probe.py")


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    if os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true":
        pytest.fail("DATABASE_URL is required for the cross-service contract test")
    pytest.skip("DATABASE_URL is not configured")


@contextmanager
def _separate_role_database(admin_url: str):
    suffix = uuid4().hex
    database = f"rag_topology_{suffix}"
    bootstrap_login = f"rag_bootstrap_{suffix}"
    migration_login = f"rag_migration_{suffix}"
    reader_login = f"rag_reader_{suffix}"
    auth_login = f"rag_auth_{suffix}"
    password = uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN CREATEROLE PASSWORD {}").format(
                sql.Identifier(bootstrap_login), sql.Literal(password)
            )
        )
        if not connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='rag_migrator'"
        ).fetchone():
            connection.execute(
                """CREATE ROLE rag_migrator
                NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
                NOREPLICATION NOBYPASSRLS"""
            )
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(bootstrap_login)
            )
        )
        for group in ("rag_reader", "rag_migrator", "rag_auth_audit"):
            if connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (group,)
            ).fetchone():
                connection.execute(
                    sql.SQL("GRANT {} TO {} WITH ADMIN OPTION").format(
                        sql.Identifier(group), sql.Identifier(bootstrap_login)
                    )
                )
    admin_database_url = make_conninfo(admin_url, dbname=database)
    with psycopg.connect(admin_database_url) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def url(login: str) -> str:
        return make_conninfo(
            admin_url,
            dbname=database,
            user=login,
            password=password,
        )

    urls = {
        "bootstrap": url(bootstrap_login),
        "migration": url(migration_login),
        "reader": url(reader_login),
        "auth": url(auth_login),
    }
    try:
        yield (
            urls,
            {
                "bootstrap": bootstrap_login,
                "migration": migration_login,
                "reader": reader_login,
                "auth": auth_login,
                "password": password,
            },
        )
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database)
                )
            )
            for role in (migration_login, reader_login, auth_login, bootstrap_login):
                connection.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                )


def _run_backend_migrations(database_url: str) -> None:
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


def _backend_http(database_url: str, method: str, path: str, body=None) -> dict:
    result = subprocess.run(
        [sys.executable, str(BACKEND_HTTP_PROBE), method, path, json.dumps(body)],
        cwd=ROOT,
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "APP_ENV": "staging",
            "ADMIN_API_KEY": "cross-service-admin-secret",
            "PUBLIC_ASSISTANT_CHAT_ENABLED": "true",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    marker = "HTTP_PROBE_RESULT="
    line = next(line for line in result.stdout.splitlines() if line.startswith(marker))
    return json.loads(line.removeprefix(marker))


def _create_login(connection, login: str, password: str, group: str) -> None:
    connection.execute(
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(login), sql.Literal(password)
        )
    )
    connection.execute(
        sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(login))
    )


class ForbiddenRuntimeWork:
    provider_calls = 0
    retrieval_calls = 0
    audit_writes = 0
    cache_writes = 0

    def embedding(self, *_args, **_kwargs):
        self.provider_calls += 1
        raise AssertionError("provider must not run during maintenance")

    text = embedding

    def search(self, **_kwargs):
        self.retrieval_calls += 1
        raise AssertionError("retrieval must not run during maintenance")

    def list(self, _limit):
        return []

    def latest(self, **_kwargs):
        return None

    def write(self, **_kwargs):
        self.audit_writes += 1
        raise AssertionError("audit must not run during maintenance")

    def get(self, *_args, **_kwargs):
        return None

    def set(self, *_args, **_kwargs):
        self.cache_writes += 1
        raise AssertionError("cache must not run during maintenance")

    def close(self):
        pass


def test_separate_ownership_topology_and_cross_service_maintenance_http(monkeypatch):
    admin_url = _database_url()
    with _separate_role_database(admin_url) as (urls, roles):
        _run_backend_migrations(urls["bootstrap"])
        reader_sql = (
            ROOT / "apps/backend/infrastructure/database/rag_read_role.sql"
        ).read_text()
        migration_owner_sql = (
            ROOT / "apps/rag-backend/migration_owner_role.sql"
        ).read_text()
        auth_sql = (ROOT / "apps/rag-backend/auth_audit_role.sql").read_text()

        with psycopg.connect(urls["bootstrap"]) as connection:
            connection.execute(reader_sql)
            connection.execute(migration_owner_sql)
            _create_login(
                connection,
                roles["migration"],
                roles["password"],
                "rag_migrator",
            )
            _create_login(connection, roles["reader"], roles["password"], "rag_reader")
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(roles["auth"]), sql.Literal(roles["password"])
                )
            )

        assert migrations.upgrade(urls["migration"]) == [
            "20260907_001_create_rag_audit_logs"
        ]
        with psycopg.connect(urls["bootstrap"]) as connection:
            connection.execute(auth_sql)
            connection.execute(
                sql.SQL("GRANT rag_auth_audit TO {}").format(
                    sql.Identifier(roles["auth"])
                )
            )
            owners = dict(
                connection.execute(
                    """SELECT tablename,tableowner FROM pg_tables
                    WHERE schemaname='rag'"""
                ).fetchall()
            )
            assert owners == {
                "audit_logs": "rag_migrator",
                "schema_migrations": "rag_migrator",
            }
            role_capabilities = {
                row[0]: row[1:]
                for row in connection.execute(
                    """SELECT rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole
                    FROM pg_roles WHERE rolname = ANY(%s)""",
                    (
                        [
                            roles["bootstrap"],
                            roles["migration"],
                            roles["reader"],
                            roles["auth"],
                        ],
                    ),
                ).fetchall()
            }
            assert role_capabilities == {
                roles["bootstrap"]: (True, False, False, True),
                roles["migration"]: (True, False, False, False),
                roles["reader"]: (True, False, False, False),
                roles["auth"]: (True, False, False, False),
            }
            legacy_audit_count = connection.execute(
                "SELECT count(*) FROM public.audit_logs"
            ).fetchone()[0]

            assistant_id = uuid4()
            document_id = f"cross-service-document-{uuid4()}"
            chunk_id = f"cross-service-chunk-{uuid4()}"
            embedding = [1.0, 0.0] + [0.0] * 1534
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

        @contextmanager
        def reader_connection(*_args, **_kwargs):
            with psycopg.connect(urls["reader"]) as connection:
                yield connection

        @contextmanager
        def auth_connection(*_args, **_kwargs):
            with psycopg.connect(urls["auth"]) as connection:
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

        for runtime_url in (urls["reader"], urls["auth"]):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                migrations.upgrade(runtime_url)
        for database_url, statement in (
            (urls["reader"], "UPDATE documents SET retrieval_state='disabled'"),
            (urls["reader"], "CREATE TABLE reader_forbidden(id integer)"),
            (urls["reader"], "CREATE SCHEMA reader_forbidden_schema"),
            (urls["auth"], "SELECT id FROM documents"),
            (urls["auth"], "ALTER TABLE rag.audit_logs ADD COLUMN forbidden text"),
            (urls["auth"], "DROP TABLE rag.audit_logs"),
            (urls["auth"], "CREATE SCHEMA auth_forbidden_schema"),
            (
                urls["auth"],
                "UPDATE operations_runtime_state SET maintenance_enabled=TRUE",
            ),
            (urls["migration"], "SELECT id FROM public.documents"),
            (urls["migration"], "CREATE SCHEMA migration_forbidden_schema"),
        ):
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                psycopg.connect(database_url) as connection,
            ):
                connection.execute(statement)

        configured = replace(
            rag_main.settings,
            knowledge_database_url=urls["reader"],
            auth_audit_database_url=urls["auth"],
            openai_api_key="configured-without-readiness-call",
            disable_cache=True,
        )
        monkeypatch.setattr(rag_main, "settings", configured)
        monkeypatch.setattr(infrastructure, "settings", configured)
        rag_main.rate_windows.clear()

        disabled = _backend_http(
            urls["bootstrap"],
            "PUT",
            "/admin/operations/maintenance",
            {"enabled": False},
        )
        assert disabled["status_code"] == 200
        backend_allowed = _backend_http(
            urls["bootstrap"],
            "POST",
            "/public/assistants/missing/chat",
            {"message": "hello"},
        )
        assert (
            backend_allowed["body"].get("detail", {}).get("code") != "maintenance_mode"
        )

        work = ForbiddenRuntimeWork()
        with TestClient(rag_main.app) as rag_client:
            rag_client.app.state.provider = work
            rag_client.app.state.repository = work
            rag_client.app.state.audit = work
            rag_client.app.state.cache = work
            assert (
                rag_client.post("/rag-chat", json={"message": "hello"}).status_code
                == 401
            )

            enabled = _backend_http(
                urls["bootstrap"],
                "PUT",
                "/admin/operations/maintenance",
                {"enabled": True},
            )
            assert enabled["status_code"] == 200
            backend_blocked = _backend_http(
                urls["bootstrap"],
                "POST",
                "/public/assistants/missing/chat",
                {"message": "hello"},
            )
            expected_detail = {
                "code": "maintenance_mode",
                "message": "The service is undergoing maintenance.",
            }
            assert backend_blocked["status_code"] == 503
            assert backend_blocked["body"] == {"detail": expected_detail}

            rag_blocked = rag_client.post("/rag-chat", json={"message": "hello"})
            assert rag_blocked.status_code == 503
            assert rag_blocked.json() == {"detail": expected_detail}
            assert rag_blocked.headers["Cache-Control"] == "no-store"
            assert work.provider_calls == 0
            assert work.retrieval_calls == 0
            assert work.audit_writes == 0
            assert work.cache_writes == 0

            assert (
                _backend_http(urls["bootstrap"], "GET", "/health/live")["status_code"]
                == 200
            )
            assert (
                _backend_http(
                    urls["bootstrap"], "GET", "/admin/operations/maintenance"
                )["status_code"]
                == 200
            )
            assert rag_client.get("/health/live").status_code == 200
            assert rag_client.get("/health/ready").status_code == 200
            assert rag_client.get("/audit-logs").status_code == 401

            class UnavailableMaintenance:
                def is_enabled(self, _deadline):
                    raise infrastructure.MaintenanceStateUnavailable

            real_maintenance = rag_client.app.state.maintenance
            rag_client.app.state.maintenance = UnavailableMaintenance()
            unavailable = rag_client.post("/rag-chat", json={"message": "hello"})
            assert unavailable.status_code == 503
            assert unavailable.json()["detail"] == {
                "code": "maintenance_state_unavailable",
                "message": "Service availability cannot currently be determined.",
            }
            rag_client.app.state.maintenance = real_maintenance

            recovered = _backend_http(
                urls["bootstrap"],
                "PUT",
                "/admin/operations/maintenance",
                {"enabled": False},
            )
            assert recovered["status_code"] == 200
            backend_recovered = _backend_http(
                urls["bootstrap"],
                "POST",
                "/public/assistants/missing/chat",
                {"message": "hello"},
            )
            assert (
                backend_recovered["body"].get("detail", {}).get("code")
                != "maintenance_mode"
            )
            assert (
                rag_client.post("/rag-chat", json={"message": "hello"}).status_code
                == 401
            )

        with psycopg.connect(urls["bootstrap"]) as connection:
            assert (
                connection.execute("SELECT count(*) FROM public.audit_logs").fetchone()[
                    0
                ]
                == legacy_audit_count
            )
