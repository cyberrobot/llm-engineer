import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import migrations


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    if os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true":
        pytest.fail("DATABASE_URL is required for RAG migration tests")
    pytest.skip("DATABASE_URL is not configured")


def _require_clean_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        row = connection.execute("SELECT to_regnamespace('rag')").fetchone()
        if row is not None and row[0]:
            if os.getenv("RAG_BACKEND_POSTGRES_REQUIRED") == "true":
                pytest.fail("RAG migration tests require a clean disposable database")
            pytest.skip("rag schema already exists; refusing destructive test setup")


def test_upgrade_is_versioned_repeatable_and_does_not_touch_backend_tables():
    database_url = _database_url()
    _require_clean_database(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS public.rag_migration_ownership_sentinel (id integer)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS public.audit_logs (
            id BIGSERIAL PRIMARY KEY, timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_role TEXT NOT NULL, question TEXT NOT NULL,
            queries JSONB NOT NULL DEFAULT '[]', reply JSONB NOT NULL DEFAULT '{}',
            retrieved_chunks JSONB NOT NULL DEFAULT '[]',
            reranked_chunks JSONB NOT NULL DEFAULT '[]',
            evaluation JSONB NOT NULL DEFAULT '{}', metrics JSONB NOT NULL DEFAULT '{}')"""
        )
        connection.execute(
            """INSERT INTO public.audit_logs (user_role,question)
            VALUES ('doctor','legacy ownership sentinel')"""
        )

    assert migrations.upgrade(database_url) == ["20260907_001_create_rag_audit_logs"]
    assert migrations.upgrade(database_url) == []
    assert migrations.status(database_url) == ["20260907_001_create_rag_audit_logs"]

    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT to_regclass('rag.audit_logs')").fetchone()[0]
        assert connection.execute(
            "SELECT to_regclass('rag.audit_logs_timestamp_idx')"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT to_regclass('public.rag_migration_ownership_sentinel')"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT question FROM public.audit_logs WHERE question='legacy ownership sentinel'"
        ).fetchone() == ("legacy ownership sentinel",)
        connection.execute(
            "DELETE FROM public.audit_logs WHERE question='legacy ownership sentinel'"
        )
        connection.execute("DROP SCHEMA rag CASCADE")
        connection.execute("DROP TABLE public.rag_migration_ownership_sentinel")


def test_failed_migration_rolls_back_schema_and_version(monkeypatch):
    database_url = _database_url()
    _require_clean_database(database_url)

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (("broken", "CREATE TABLE rag.partial(id integer); SELECT missing_column;"),),
    )

    with pytest.raises(psycopg.Error):
        migrations.upgrade(database_url)

    with psycopg.connect(database_url) as connection:
        assert (
            connection.execute("SELECT to_regclass('rag.partial')").fetchone()[0]
            is None
        )
        assert (
            connection.execute(
                "SELECT to_regclass('rag.schema_migrations')"
            ).fetchone()[0]
            is None
        )
