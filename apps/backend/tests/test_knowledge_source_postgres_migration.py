from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection
from infrastructure.database.migrations.knowledge_source_management import downgrade, upgrade


def _require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def _create_baseline(cursor) -> None:
    cursor.execute("CREATE TABLE assistants (id TEXT PRIMARY KEY)")
    cursor.execute("""
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            assistant_id TEXT NOT NULL REFERENCES assistants(id),
            UNIQUE (id, assistant_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE document_ingestion_jobs (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            status TEXT NOT NULL
        )
    """)


def _set_schema(cursor, schema: str) -> None:
    cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))


def test_migration_upgrades_repeats_downgrades_reupgrades_and_enforces_constraints():
    _require_database()
    schema = f"knowledge_source_migration_{uuid4().hex}"
    assistant_id = str(uuid4())
    other_assistant_id = str(uuid4())
    document_id = str(uuid4())

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            _set_schema(cursor, schema)
            _create_baseline(cursor)
            cursor.execute(
                "INSERT INTO assistants (id) VALUES (%s), (%s)",
                (assistant_id, other_assistant_id),
            )
            cursor.execute(
                "INSERT INTO documents (id, assistant_id) VALUES (%s, %s)",
                (document_id, assistant_id),
            )

            upgrade(cursor)
            upgrade(cursor)
            assert cursor.execute("SELECT to_regclass('knowledge_sources')").fetchone()[0]
            assert cursor.execute(
                "SELECT to_regclass('knowledge_source_active_job_unique_idx')"
            ).fetchone()[0]

            source_values = (
                str(uuid4()),
                assistant_id,
                document_id,
                "a" * 64,
            )
            cursor.execute(
                """INSERT INTO knowledge_sources
                   (id, assistant_id, source_type, name, retrieval_state, direct_text,
                    document_id, content_version)
                   VALUES (%s, %s, 'direct_text', 'Guide', 'disabled', 'Safe text', %s, %s)""",
                source_values,
            )
            cursor.execute("SAVEPOINT duplicate_source")
            with pytest.raises(psycopg.errors.UniqueViolation):
                cursor.execute(
                    """INSERT INTO knowledge_sources
                       (id, assistant_id, source_type, name, retrieval_state, direct_text,
                        document_id, content_version)
                       VALUES (%s, %s, 'direct_text', 'Copy', 'enabled', 'Other', %s, %s)""",
                    (str(uuid4()), assistant_id, document_id, "b" * 64),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT duplicate_source")

            downgrade(cursor)
            assert cursor.execute("SELECT to_regclass('knowledge_sources')").fetchone()[0] is None
            upgrade(cursor)
            assert cursor.execute("SELECT to_regclass('knowledge_sources')").fetchone()[0]
        connection.rollback()


def test_migration_reports_documents_with_duplicate_active_jobs():
    _require_database()
    schema = f"knowledge_source_duplicates_{uuid4().hex}"
    assistant_id = str(uuid4())
    document_id = str(uuid4())

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            _set_schema(cursor, schema)
            _create_baseline(cursor)
            cursor.execute("INSERT INTO assistants (id) VALUES (%s)", (assistant_id,))
            cursor.execute(
                "INSERT INTO documents (id, assistant_id) VALUES (%s, %s)",
                (document_id, assistant_id),
            )
            cursor.execute(
                """INSERT INTO document_ingestion_jobs (id, document_id, status)
                   VALUES (%s, %s, 'queued'), (%s, %s, 'running')""",
                (str(uuid4()), document_id, str(uuid4()), document_id),
            )

            cursor.execute("SAVEPOINT unsafe_upgrade")
            with pytest.raises(psycopg.errors.UniqueViolation) as error:
                upgrade(cursor)

            assert "Cannot enforce one active ingestion job per document" in str(error.value)
            assert document_id in str(error.value)
            cursor.execute("ROLLBACK TO SAVEPOINT unsafe_upgrade")
            assert cursor.execute(
                "SELECT to_regclass('knowledge_source_active_job_unique_idx')"
            ).fetchone()[0] is None
        connection.rollback()
