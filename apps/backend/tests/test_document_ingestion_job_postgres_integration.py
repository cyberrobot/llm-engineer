from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from assistant.application.ingestion_job_service import DocumentIngestionJobService
from assistant.domain.document_ingestion_job import IngestionStep
from assistant.infrastructure.repositories.document_ingestion_job import (
    PostgresDocumentIngestionJobRepository,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.ingestion_job_domain import downgrade, upgrade
from infrastructure.database.migrations.ingestion_pipeline_checkpoint import (
    downgrade as downgrade_checkpoint,
)
from infrastructure.database.migrations.ingestion_pipeline_checkpoint import (
    upgrade as upgrade_checkpoint,
)


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def create_document(document_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO documents (id, doc_type) VALUES (%s, 'test')", (document_id,)
        )


def delete_document(document_id: str) -> None:
    with suppress(Exception), get_connection() as connection:
        connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_postgres_repository_persists_queries_filters_and_enforces_retry_constraint():
    require_database()
    init_db()
    document_id = str(uuid4())
    create_document(document_id)
    service = DocumentIngestionJobService(PostgresDocumentIngestionJobRepository())

    try:
        with get_connection() as connection:
            connection.execute(
                "UPDATE documents SET source_url = %s, access_roles = %s::jsonb WHERE id = %s",
                ("https://example.com/source", '["manager"]', document_id),
            )
        created = service.create(document_id, idempotency_key=f"integration-{uuid4()}")

        created.mark_running()
        created.set_current_step(IngestionStep.parse)
        repository = PostgresDocumentIngestionJobRepository()
        repository.update(created)

        assert service.get(created.id) == created
        source = repository.get_document_source(document_id)
        assert source is not None
        assert source.source_url == "https://example.com/source"
        assert source.access_roles == ("manager",)
        listed = service.list(limit=10, offset=0, status=created.status, document_id=document_id)
        assert listed.items == [created]
        assert listed.total == 1

        invalid_job_id = str(uuid4())
        with pytest.raises(psycopg.errors.CheckViolation):
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO document_ingestion_jobs (
                        id, document_id, status, retry_count, created_at, updated_at
                    ) VALUES (%s, %s, 'queued', -1, NOW(), NOW())
                    """,
                    (invalid_job_id, document_id),
                )
        with get_connection() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM document_ingestion_jobs WHERE id = %s",
                    (invalid_job_id,),
                ).fetchone()[0]
                == 0
            )
    finally:
        delete_document(document_id)


def test_concurrent_idempotent_creation_returns_one_job_and_leaves_one_row():
    require_database()
    init_db()
    document_id = str(uuid4())
    key = f"concurrent-{uuid4()}"
    create_document(document_id)

    def create() -> str:
        service = DocumentIngestionJobService(PostgresDocumentIngestionJobRepository())
        return str(service.create(document_id, idempotency_key=key).id)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            job_ids = list(executor.map(lambda _: create(), range(2)))

        with get_connection() as connection:
            count = connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE idempotency_key = %s", (key,)
            ).fetchone()[0]
        assert job_ids[0] == job_ids[1]
        assert count == 1
    finally:
        delete_document(document_id)


def test_migration_downgrades_and_reupgrades_an_isolated_schema():
    require_database()
    schema = f"migration_{uuid4().hex}"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute("CREATE TABLE documents (id TEXT PRIMARY KEY)")
            cursor.execute("""
                CREATE TABLE document_ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            upgrade(cursor)
            upgrade_checkpoint(cursor)
            upgraded_columns = {
                row[0]
                for row in cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'document_ingestion_jobs'
                    """,
                    (schema,),
                ).fetchall()
            }
            assert {
                "current_step",
                "last_completed_step",
                "retry_count",
                "idempotency_key",
                "completed_at",
            } <= upgraded_columns

            downgrade_checkpoint(cursor)
            downgrade(cursor)
            downgraded_columns = {
                row[0]
                for row in cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'document_ingestion_jobs'
                    """,
                    (schema,),
                ).fetchall()
            }
            assert "current_step" not in downgraded_columns
            assert "last_completed_step" not in downgraded_columns

            upgrade(cursor)
            upgrade_checkpoint(cursor)
            reupgraded_columns = {
                row[0]
                for row in cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = 'document_ingestion_jobs'
                    """,
                    (schema,),
                ).fetchall()
            }
            assert "current_step" in reupgraded_columns
            assert "last_completed_step" in reupgraded_columns

        connection.rollback()
