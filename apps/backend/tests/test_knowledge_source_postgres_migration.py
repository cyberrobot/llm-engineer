import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection
from infrastructure.database.migrations.knowledge_source_management import downgrade, upgrade


def _require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for knowledge-source PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
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


def _expect_constraint(cursor, statement: str, parameters: tuple, name: str) -> None:
    cursor.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(name)))
    with pytest.raises(psycopg.IntegrityError):
        cursor.execute(statement, parameters)
    cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(name)))


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
            assert (
                cursor.execute(
                    "SELECT to_regclass('knowledge_source_active_job_unique_idx')"
                ).fetchone()[0]
                is None
            )

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


def test_migration_enforces_knowledge_source_constraint_matrix():
    _require_database()
    schema = f"knowledge_source_constraints_{uuid4().hex}"
    assistants = [str(uuid4()), str(uuid4())]
    documents = [str(uuid4()) for _ in range(8)]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            _set_schema(cursor, schema)
            _create_baseline(cursor)
            cursor.executemany(
                "INSERT INTO assistants (id) VALUES (%s)", [(x,) for x in assistants]
            )
            cursor.executemany(
                "INSERT INTO documents (id, assistant_id) VALUES (%s, %s)",
                [(document, assistants[index % 2]) for index, document in enumerate(documents)],
            )
            upgrade(cursor)

            insert_source = """INSERT INTO knowledge_sources
                (id, assistant_id, source_type, name, retrieval_state, direct_text,
                 normalized_url, document_id, content_version, creation_idempotency_key,
                 creation_request_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            digest = "a" * 64
            first_source = str(uuid4())
            cursor.execute(
                insert_source,
                (
                    first_source,
                    assistants[0],
                    "url",
                    "Guide",
                    "enabled",
                    None,
                    "https://example.com/guide",
                    documents[0],
                    digest,
                    "shared-key",
                    digest,
                ),
            )
            _expect_constraint(
                cursor,
                insert_source,
                (
                    str(uuid4()),
                    assistants[0],
                    "url",
                    "Duplicate",
                    "enabled",
                    None,
                    "https://example.com/other",
                    documents[2],
                    digest,
                    "shared-key",
                    digest,
                ),
                "duplicate_creation_key",
            )
            second_source = str(uuid4())
            cursor.execute(
                insert_source,
                (
                    second_source,
                    assistants[1],
                    "url",
                    "Isolated",
                    "disabled",
                    None,
                    "https://example.com/guide",
                    documents[1],
                    digest,
                    "shared-key",
                    digest,
                ),
            )
            _expect_constraint(
                cursor,
                insert_source,
                (
                    str(uuid4()),
                    assistants[0],
                    "url",
                    "Duplicate URL",
                    "enabled",
                    None,
                    "https://example.com/guide",
                    documents[4],
                    digest,
                    None,
                    None,
                ),
                "duplicate_url",
            )

            invalid_sources = [
                ("direct_text", None, None, "Valid", "enabled", digest),
                ("direct_text", "text", "https://example.com/x", "Valid", "enabled", digest),
                ("url", "text", "https://example.com/x", "Valid", "enabled", digest),
                ("url", None, None, "Valid", "enabled", digest),
                ("direct_text", "text", None, "   ", "enabled", digest),
                ("direct_text", "text", None, "Valid", "enabled", "invalid"),
                ("direct_text", "text", None, "Valid", "hidden", digest),
            ]
            for index, (kind, text_value, url, name, state, version) in enumerate(invalid_sources):
                _expect_constraint(
                    cursor,
                    insert_source,
                    (
                        str(uuid4()),
                        assistants[0],
                        kind,
                        name,
                        state,
                        text_value,
                        url,
                        documents[6],
                        version,
                        None,
                        None,
                    ),
                    f"invalid_source_{index}",
                )
            _expect_constraint(
                cursor,
                insert_source,
                (
                    str(uuid4()),
                    assistants[0],
                    "direct_text",
                    "Second owner",
                    "enabled",
                    "text",
                    None,
                    documents[0],
                    digest,
                    None,
                    None,
                ),
                "duplicate_document_owner",
            )

            active_job = str(uuid4())
            cursor.execute(
                "INSERT INTO document_ingestion_jobs (id, document_id, status) VALUES (%s,%s,'queued')",
                (active_job, documents[0]),
            )
            cursor.execute(
                "INSERT INTO document_ingestion_jobs (id, document_id, status) VALUES (%s,%s,'running')",
                (str(uuid4()), documents[0]),
            )
            terminal_jobs = []
            for status in ("completed", "failed", "cancelled", "completed"):
                job_id = str(uuid4())
                terminal_jobs.append(job_id)
                cursor.execute(
                    "INSERT INTO document_ingestion_jobs (id, document_id, status) VALUES (%s,%s,%s)",
                    (job_id, documents[0], status),
                )

            insert_receipt = """INSERT INTO knowledge_source_reingestion_requests
                (assistant_id, source_id, idempotency_key, request_hash, ingestion_job_id)
                VALUES (%s,%s,%s,%s,%s)"""
            cursor.execute(
                insert_receipt,
                (assistants[0], first_source, "receipt-key", digest, terminal_jobs[0]),
            )
            _expect_constraint(
                cursor,
                insert_receipt,
                (assistants[0], first_source, "receipt-key", digest, terminal_jobs[1]),
                "duplicate_receipt",
            )
            cursor.execute(
                insert_receipt,
                (assistants[1], second_source, "receipt-key", digest, active_job),
            )
            for index, values in enumerate(
                (
                    (str(uuid4()), first_source, "bad-assistant", digest, terminal_jobs[1]),
                    (assistants[0], str(uuid4()), "bad-source", digest, terminal_jobs[1]),
                    (assistants[0], first_source, "bad-job", digest, str(uuid4())),
                )
            ):
                _expect_constraint(cursor, insert_receipt, values, f"invalid_receipt_{index}")
            cursor.execute("DELETE FROM document_ingestion_jobs WHERE id=%s", (terminal_jobs[0],))
            assert (
                cursor.execute(
                    "SELECT count(*) FROM knowledge_source_reingestion_requests WHERE assistant_id=%s",
                    (assistants[0],),
                ).fetchone()[0]
                == 0
            )
        connection.rollback()


def test_migration_removes_draft_active_job_index_and_allows_legacy_active_jobs():
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
                   VALUES (%s, %s, 'queued')""",
                (str(uuid4()), document_id),
            )

            cursor.execute("""CREATE UNIQUE INDEX knowledge_source_active_job_unique_idx
                ON document_ingestion_jobs(document_id)
                WHERE status IN ('queued', 'running')""")
            upgrade(cursor)
            cursor.execute(
                """INSERT INTO document_ingestion_jobs (id, document_id, status)
                   VALUES (%s, %s, 'running')""",
                (str(uuid4()), document_id),
            )
            assert (
                cursor.execute(
                    "SELECT to_regclass('knowledge_source_active_job_unique_idx')"
                ).fetchone()[0]
                is None
            )
            assert (
                cursor.execute(
                    """SELECT count(*) FROM document_ingestion_jobs
                   WHERE document_id=%s AND status IN ('queued', 'running')""",
                    (document_id,),
                ).fetchone()[0]
                == 2
            )
        connection.rollback()
