import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from assistant.application.file_ingestion import FileIngestionRequest, FileIngestionService
from assistant.domain.file_fingerprint import ContentStatus, FileFingerprint
from assistant.infrastructure.repositories.file_ingestion import PostgresFileIngestionRepository
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.file_integrity_deduplication import downgrade, upgrade


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def upload_request(*, key: str | None = None) -> FileIngestionRequest:
    content = b"%PDF-1.7 concurrent policy"
    return FileIngestionRequest(
        doc_type="policy",
        access_roles=(f"test-{uuid4()}",),
        upload_path=f"/private/test/{uuid4()}.pdf",
        original_filename="policy.pdf",
        mime_type="application/pdf",
        fingerprint=FileFingerprint("sha256", hashlib.sha256(content).hexdigest(), len(content)),
        checksum_calculated_at=datetime.now(timezone.utc),
        idempotency_key=key,
    )


def test_concurrent_identical_submissions_converge_on_one_document_and_active_job():
    require_database()
    init_db()
    shared = upload_request()
    scope = (f"concurrent-{uuid4()}",)

    def submit(index: int):
        request = FileIngestionRequest(
            **{
                **shared.__dict__,
                "access_roles": scope,
                "upload_path": f"/private/test/concurrent-{index}.pdf",
            }
        )
        return FileIngestionService(PostgresFileIngestionRepository()).submit(request)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))

        assert results[0].document_id == results[1].document_id
        assert results[0].ingestion_job_id == results[1].ingestion_job_id
        assert {result.content_status for result in results} == {
            ContentStatus.new_content,
            ContentStatus.duplicate_content,
        }
        with get_connection() as connection:
            document_count = connection.execute(
                """
                SELECT count(*) FROM documents
                WHERE access_roles = %s::jsonb AND checksum = %s
                """,
                (f'["{scope[0]}"]', shared.fingerprint.checksum),
            ).fetchone()[0]
            job_count = connection.execute(
                """
                SELECT count(*) FROM document_ingestion_jobs
                WHERE document_id = %s AND status IN ('queued', 'running')
                """,
                (results[0].document_id,),
            ).fetchone()[0]
            chunk_count = connection.execute(
                "SELECT count(*) FROM chunks WHERE doc_id = %s",
                (results[0].document_id,),
            ).fetchone()[0]
        assert document_count == 1
        assert job_count == 1
        assert chunk_count == 0
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM documents WHERE access_roles = %s::jsonb", (f'["{scope[0]}"]',)
            )


def test_file_integrity_migration_preserves_legacy_rows_and_is_reversible():
    require_database()
    schema = f"fingerprint_migration_{uuid4().hex}"

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            cursor.execute("""
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    access_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE document_ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    idempotency_key TEXT
                )
            """)
            cursor.execute("INSERT INTO documents (id) VALUES ('legacy-document')")

            upgrade(cursor)
            legacy = cursor.execute(
                """
                SELECT checksum_algorithm, checksum, file_size_bytes
                FROM documents WHERE id = 'legacy-document'
                """
            ).fetchone()
            assert legacy == (None, None, None)

            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    cursor.execute(
                        "UPDATE documents SET checksum_algorithm = 'sha256' WHERE id = 'legacy-document'"
                    )

            downgrade(cursor)
            assert (
                cursor.execute("SELECT to_regclass('ingestion_file_requests')").fetchone()[0]
                is None
            )
            upgrade(cursor)
            assert cursor.execute("SELECT to_regclass('ingestion_file_requests')").fetchone()[0]

        connection.rollback()
