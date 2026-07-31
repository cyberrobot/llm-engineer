import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

import psycopg
import pytest

from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.maintenance.ingestion import IngestionMaintenanceSettings, MaintenanceCategory
from assistant.maintenance.repository import PostgresIngestionMaintenanceRepository
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, rows, rowcount=None):
        self.rows = rows
        self.rowcount = len(rows) if rowcount is None else rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RecordingConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, parameters=()):
        self.queries.append((" ".join(query.split()), parameters))
        return Result(self.rows)


class ScriptedConnection(RecordingConnection):
    def __init__(self, results):
        super().__init__([])
        self.results = list(results)

    def execute(self, query, parameters=()):
        self.queries.append((" ".join(query.split()), parameters))
        return self.results.pop(0)


def test_terminal_cleanup_query_revalidates_every_destructive_safety_boundary():
    connection = RecordingConnection([("old-job", NOW - timedelta(days=200))])
    repository = PostgresIngestionMaintenanceRepository(lambda: connection)

    result = repository.process_batch(
        MaintenanceCategory.terminal_job_retention,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=False,
        cursor=None,
    )

    sql = connection.queries[0][0]
    assert "DELETE FROM document_ingestion_jobs" in sql
    assert "status = 'completed'" in sql
    assert "status = 'failed'" in sql
    assert "status = 'cancelled'" in sql
    assert "jobs.worker_id IS NULL" in sql
    assert "jobs.lease_expires_at IS NULL OR jobs.lease_expires_at <=" in sql
    assert "attempts.status IN ('running', 'interrupted')" in sql
    assert "documents.last_ingestion_job_id = jobs.id" in sql
    assert "chunks.ingestion_job_id = jobs.id" in sql
    assert "ingestion_persistence_results" in sql
    assert "ingestion_file_requests" in sql
    assert "DELETE FROM ingestion_persistence_results" in sql
    assert "FOR UPDATE OF jobs SKIP LOCKED" in sql
    assert result.records_deleted == 1


def test_module_entrypoint_category_identity_does_not_change_dispatch():
    class EntrypointCategory(str, Enum):
        category = "SUPERSEDED_REPRESENTATION_RETENTION"

    repository = PostgresIngestionMaintenanceRepository(lambda: None)

    result = repository.process_batch(
        EntrypointCategory.category,  # type: ignore[arg-type]
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=True,
        cursor=None,
    )

    assert result.stopped_reason == "not_applicable_current_schema"


def test_terminal_cleanup_dry_run_uses_same_eligibility_without_delete():
    connection = RecordingConnection([("old-job", NOW - timedelta(days=200))])
    repository = PostgresIngestionMaintenanceRepository(lambda: connection)

    result = repository.process_batch(
        MaintenanceCategory.terminal_job_retention,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=True,
        cursor=None,
    )

    assert "DELETE" not in connection.queries[0][0]
    assert result.candidates_found == 1
    assert result.records_deleted == 0
    assert result.records_skipped == 1


class TemporarySourceRepository(PostgresIngestionMaintenanceRepository):
    def __init__(self, upload_dir: Path, referenced: set[str]):
        super().__init__(lambda: None, upload_dir=upload_dir)
        self.referenced = referenced

    def _upload_path_is_referenced(self, path):
        return path.name in self.referenced


def _old_file(path: Path):
    path.write_bytes(b"fictional pdf")
    old = NOW.timestamp() - 48 * 60 * 60
    os.utime(path, (old, old))


def test_temporary_source_cleanup_only_deletes_unreferenced_managed_uuid_pdf(tmp_path):
    orphan = tmp_path / "11111111-1111-4111-8111-111111111111.pdf"
    referenced = tmp_path / "22222222-2222-4222-8222-222222222222.pdf"
    unsafe = tmp_path / "customer-provided.pdf"
    _old_file(orphan)
    _old_file(referenced)
    _old_file(unsafe)
    repository = TemporarySourceRepository(tmp_path, {referenced.name})

    dry_run = repository.process_batch(
        MaintenanceCategory.temporary_source_cleanup,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=True,
        cursor=None,
    )
    assert dry_run.records_deleted == 0
    assert orphan.exists()
    executed = repository.process_batch(
        MaintenanceCategory.temporary_source_cleanup,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=False,
        cursor=None,
    )

    assert executed.records_deleted == 1
    assert not orphan.exists()
    assert referenced.exists()
    assert unsafe.exists()


def test_reconciliation_completes_only_exact_active_committed_result():
    job_id = "11111111-1111-4111-8111-111111111111"
    stale_row = (
        job_id,
        "running",
        "document-1",
        "persist",
        "embed",
        2,
        NOW - timedelta(hours=1),
        "stale-worker",
        NOW - timedelta(minutes=30),
        "https://example.test/source",
        None,
    )
    connection = ScriptedConnection(
        [
            Result([stale_row]),
            Result([("document-1", {"chunks_received": 2}, job_id, 2, 2)]),
            Result([], rowcount=1),
        ]
    )
    repository = PostgresIngestionMaintenanceRepository(lambda: connection)

    result = repository.process_batch(
        MaintenanceCategory.expired_lease_recovery,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=False,
        cursor=None,
    )

    assert result.records_repaired == 1
    update_sql = connection.queries[-1][0]
    assert "status = 'completed'" in update_sql
    assert "last_completed_step = 'persist'" in update_sql
    assert "claim_version = claim_version + 1" in update_sql
    assert "WHERE id =" in update_sql and "status = 'running'" in update_sql


def test_reconciliation_reports_ambiguous_committed_result_without_mutation():
    job_id = "11111111-1111-4111-8111-111111111111"
    stale_row = (
        job_id,
        "running",
        "document-1",
        "persist",
        "embed",
        2,
        NOW - timedelta(hours=1),
        "stale-worker",
        NOW - timedelta(minutes=30),
        "https://example.test/source",
        None,
    )
    connection = ScriptedConnection(
        [
            Result([stale_row]),
            Result([("document-1", {"chunks_received": 2}, "different-job", 1, 2)]),
        ]
    )
    repository = PostgresIngestionMaintenanceRepository(lambda: connection)

    result = repository.process_batch(
        MaintenanceCategory.expired_lease_recovery,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=False,
        cursor=None,
    )

    assert result.records_repaired == 0
    assert result.manual_review_count == 1
    assert result.findings[0].reason_code == "committed_result_not_active_or_incomplete"
    assert len(connection.queries) == 2


def test_reset_to_queued_preserves_retry_count_and_checkpoint_columns():
    stale_row = (
        "11111111-1111-4111-8111-111111111111",
        "running",
        "document-1",
        "chunk",
        "parse",
        4,
        NOW - timedelta(hours=1),
        "stale-worker",
        NOW - timedelta(minutes=30),
        "https://example.test/source",
        None,
    )
    connection = ScriptedConnection([Result([stale_row]), Result([]), Result([], rowcount=1)])
    repository = PostgresIngestionMaintenanceRepository(lambda: connection)

    result = repository.process_batch(
        MaintenanceCategory.expired_lease_recovery,
        settings=IngestionMaintenanceSettings(),
        now=NOW,
        dry_run=False,
        cursor=None,
    )

    update_sql = connection.queries[-1][0]
    assert result.records_repaired == 1
    assert "status = 'queued'" in update_sql
    assert "retry_count" not in update_sql
    assert "last_completed_step" not in update_sql
    assert "current_step =" not in update_sql


def _postgres_available():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def test_postgres_terminal_cleanup_preserves_recent_job_and_converges():
    _postgres_available()
    init_db()
    document_id = "maintenance-test-document"
    old_job = "11111111-1111-4111-8111-111111111111"
    recent_job = "22222222-2222-4222-8222-222222222222"
    try:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            connection.execute(
                """INSERT INTO documents (id, doc_type, assistant_id)
                   VALUES (%s, 'test', %s)""",
                (document_id, str(REDMOOR_ASSISTANT_ID)),
            )
            for job_id, completed_at in (
                (old_job, NOW - timedelta(days=181)),
                (recent_job, NOW - timedelta(days=1)),
            ):
                connection.execute(
                    """
                    INSERT INTO document_ingestion_jobs (
                        id, document_id, status, created_at, started_at, completed_at, updated_at
                    ) VALUES (%s, %s, 'completed', %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        document_id,
                        completed_at - timedelta(hours=1),
                        completed_at - timedelta(minutes=30),
                        completed_at,
                        completed_at,
                    ),
                )
        repository = PostgresIngestionMaintenanceRepository()
        settings = IngestionMaintenanceSettings(batch_size=10)
        dry = repository.process_batch(
            MaintenanceCategory.terminal_job_retention,
            settings=settings,
            now=NOW,
            dry_run=True,
            cursor=None,
        )
        execute = repository.process_batch(
            MaintenanceCategory.terminal_job_retention,
            settings=settings,
            now=NOW,
            dry_run=False,
            cursor=None,
        )
        repeated = repository.process_batch(
            MaintenanceCategory.terminal_job_retention,
            settings=settings,
            now=NOW,
            dry_run=False,
            cursor=None,
        )

        assert dry.candidates_found == 1 and dry.records_deleted == 0
        assert execute.records_deleted == 1
        assert repeated.candidates_found == 0
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT id FROM document_ingestion_jobs WHERE document_id = %s", (document_id,)
            ).fetchall()
        assert rows == [(recent_job,)]
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_postgres_terminal_cleanup_rolls_back_entire_batch_after_delete_failure():
    _postgres_available()
    init_db()
    document_id = "maintenance-rollback-document"
    first_job = "33333333-3333-4333-8333-333333333333"
    failing_job = "44444444-4444-4444-8444-444444444444"
    try:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            connection.execute(
                """INSERT INTO documents (id, doc_type, assistant_id)
                   VALUES (%s, 'test', %s)""",
                (document_id, str(REDMOOR_ASSISTANT_ID)),
            )
            completed_at = NOW - timedelta(days=181)
            for job_id in (first_job, failing_job):
                connection.execute(
                    """
                    INSERT INTO document_ingestion_jobs (
                        id, document_id, status, created_at, started_at, completed_at, updated_at
                    ) VALUES (%s, %s, 'completed', %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        document_id,
                        completed_at - timedelta(hours=1),
                        completed_at - timedelta(minutes=30),
                        completed_at,
                        completed_at,
                    ),
                )
            connection.execute(
                f"""
                CREATE OR REPLACE FUNCTION maintenance_test_reject_delete()
                RETURNS trigger AS $$
                BEGIN
                    IF OLD.id = '{failing_job}' THEN
                        RAISE EXCEPTION 'fictional maintenance delete failure';
                    END IF;
                    RETURN OLD;
                END
                $$ LANGUAGE plpgsql
                """
            )
            connection.execute(
                """
                CREATE TRIGGER maintenance_test_reject_delete_trigger
                BEFORE DELETE ON document_ingestion_jobs
                FOR EACH ROW EXECUTE FUNCTION maintenance_test_reject_delete()
                """
            )

        repository = PostgresIngestionMaintenanceRepository()
        with pytest.raises(RuntimeError, match="cleanup failed"):
            repository.process_batch(
                MaintenanceCategory.terminal_job_retention,
                settings=IngestionMaintenanceSettings(batch_size=10),
                now=NOW,
                dry_run=False,
                cursor=None,
            )
        with get_connection() as connection:
            count = connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE document_id = %s",
                (document_id,),
            ).fetchone()[0]
        assert count == 2
    finally:
        with get_connection() as connection:
            connection.execute(
                "DROP TRIGGER IF EXISTS maintenance_test_reject_delete_trigger "
                "ON document_ingestion_jobs"
            )
            connection.execute("DROP FUNCTION IF EXISTS maintenance_test_reject_delete()")
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_postgres_advisory_lock_blocks_same_category_but_not_independent_category():
    _postgres_available()
    first = PostgresIngestionMaintenanceRepository()
    second = PostgresIngestionMaintenanceRepository()
    try:
        assert first.acquire_lock(MaintenanceCategory.terminal_job_retention, 0)
        assert not second.acquire_lock(MaintenanceCategory.terminal_job_retention, 0)
        assert second.acquire_lock(MaintenanceCategory.step_history_retention, 0)
    finally:
        first.release_lock(MaintenanceCategory.terminal_job_retention)
        second.release_lock(MaintenanceCategory.terminal_job_retention)
        second.release_lock(MaintenanceCategory.step_history_retention)
