import psycopg
import pytest

from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.ingestion_observability import downgrade, upgrade


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(" ".join(query.split()))


def test_observability_migration_adds_attempt_history_constraints_and_query_indexes():
    cursor = RecordingCursor()
    upgrade(cursor)
    sql = "\n".join(cursor.queries)

    assert "CREATE TABLE IF NOT EXISTS ingestion_step_executions" in sql
    assert "UNIQUE (ingestion_job_id, step, attempt_number)" in sql
    assert "status IN ('running', 'completed', 'failed', 'interrupted')" in sql
    assert "duration_ms >= 0" in sql
    assert "document_ingestion_jobs_status_created_idx" in sql
    assert "document_ingestion_jobs_document_created_idx" in sql

    downgrade(cursor)
    downgraded = "\n".join(cursor.queries)
    assert "DROP TABLE IF EXISTS ingestion_step_executions" in downgraded


def test_observability_migration_downgrades_and_reapplies_on_postgres():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    init_db()
    try:
        with get_connection() as connection, connection.cursor() as cursor:
            downgrade(cursor)
            assert (
                connection.execute("SELECT to_regclass('ingestion_step_executions')").fetchone()[0]
                is None
            )
            upgrade(cursor)
            assert (
                connection.execute("SELECT to_regclass('ingestion_step_executions')").fetchone()[0]
                == "ingestion_step_executions"
            )
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
                ).fetchall()
            }
            assert "document_ingestion_jobs_status_created_idx" in indexes
            assert "document_ingestion_jobs_document_created_idx" in indexes
    finally:
        init_db()
