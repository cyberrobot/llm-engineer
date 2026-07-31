import psycopg
import pytest

from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.ingestion_operational_maintenance import (
    downgrade,
    upgrade,
)


class RecordingCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query):
        self.queries.append(" ".join(query.split()))


def test_maintenance_migration_adds_only_queries_needed_for_bounded_candidates():
    cursor = RecordingCursor()

    upgrade(cursor)
    sql = "\n".join(cursor.queries)

    assert "document_ingestion_jobs_terminal_retention_idx" in sql
    assert "status, completed_at, id" in sql
    assert "ingestion_step_executions_retention_idx" in sql
    assert "completed_at, id" in sql
    assert "documents_upload_path_idx" in sql
    assert "WHERE upload_path IS NOT NULL" in sql
    assert "CREATE TABLE" not in sql

    downgrade(cursor)
    assert "DROP INDEX IF EXISTS documents_upload_path_idx" in "\n".join(cursor.queries)


def test_maintenance_migration_downgrades_and_reapplies_without_changing_data():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    init_db()
    with get_connection() as connection, connection.cursor() as cursor:
        before = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
        downgrade(cursor)
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            ).fetchall()
        }
        assert "document_ingestion_jobs_terminal_retention_idx" not in indexes
        upgrade(cursor)
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            ).fetchall()
        }
        assert "document_ingestion_jobs_terminal_retention_idx" in indexes
        assert "ingestion_step_executions_retention_idx" in indexes
        assert "documents_upload_path_idx" in indexes
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == before
