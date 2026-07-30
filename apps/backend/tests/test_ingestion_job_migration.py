from infrastructure.database.migrations.file_integrity_deduplication import (
    downgrade as downgrade_fingerprints,
)
from infrastructure.database.migrations.file_integrity_deduplication import (
    upgrade as upgrade_fingerprints,
)
from infrastructure.database.migrations.ingestion_job_domain import downgrade, upgrade
from infrastructure.database.migrations.ingestion_pipeline_checkpoint import (
    downgrade as downgrade_checkpoint,
)
from infrastructure.database.migrations.ingestion_pipeline_checkpoint import (
    upgrade as upgrade_checkpoint,
)
from infrastructure.database.migrations.ingestion_retry_recovery import (
    downgrade as downgrade_retry,
)
from infrastructure.database.migrations.ingestion_retry_recovery import upgrade as upgrade_retry


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(" ".join(query.split()))


def test_ingestion_job_migration_is_reversible_and_defines_required_constraints_and_indexes():
    cursor = RecordingCursor()

    upgrade(cursor)
    upgraded = "\n".join(cursor.queries)

    assert "ADD COLUMN IF NOT EXISTS current_step" in upgraded
    assert "CHECK (retry_count >= 0)" in upgraded
    assert "document_ingestion_jobs_status_check" in upgraded
    assert "document_ingestion_jobs_step_check" in upgraded
    assert "document_ingestion_jobs_lifecycle_check" in upgraded
    assert "document_ingestion_jobs_idempotency_key_unique_idx" in upgraded
    assert "document_ingestion_jobs_status_idx" in upgraded
    assert "document_ingestion_jobs_created_at_idx" in upgraded

    cursor.queries.clear()
    downgrade(cursor)
    downgraded = "\n".join(cursor.queries)

    assert "DROP INDEX IF EXISTS document_ingestion_jobs_idempotency_key_unique_idx" in downgraded
    assert "DROP COLUMN IF EXISTS current_step" in downgraded


def test_pipeline_checkpoint_migration_is_nullable_constrained_and_reversible():
    cursor = RecordingCursor()

    upgrade_checkpoint(cursor)
    upgraded = "\n".join(cursor.queries)

    assert "ADD COLUMN IF NOT EXISTS last_completed_step" in upgraded
    assert "document_ingestion_jobs_completed_step_check" in upgraded
    assert "last_completed_step IS NULL" in upgraded

    cursor.queries.clear()
    downgrade_checkpoint(cursor)
    downgraded = "\n".join(cursor.queries)

    assert "DROP CONSTRAINT IF EXISTS document_ingestion_jobs_completed_step_check" in downgraded
    assert "DROP COLUMN IF EXISTS last_completed_step" in downgraded


def test_retry_recovery_migration_adds_durable_attempt_state_and_is_reversible():
    cursor = RecordingCursor()

    upgrade_retry(cursor)
    upgraded = "\n".join(cursor.queries)

    assert (
        "ADD COLUMN IF NOT EXISTS current_step_attempt_count INTEGER NOT NULL DEFAULT 0" in upgraded
    )
    assert "ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ" in upgraded
    assert "CHECK (current_step_attempt_count >= 0)" in upgraded
    assert "DROP CONSTRAINT IF EXISTS document_ingestion_jobs_lifecycle_check" in upgraded
    assert "OR current_step_attempt_count > 0" in upgraded

    cursor.queries.clear()
    downgrade_retry(cursor)
    downgraded = "\n".join(cursor.queries)
    assert "DROP COLUMN IF EXISTS current_step_attempt_count" in downgraded
    assert "DROP COLUMN IF EXISTS last_attempted_at" in downgraded
    assert (
        "status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NULL"
        in downgraded
    )


def test_file_integrity_migration_adds_nullable_metadata_scoped_uniqueness_and_job_intent():
    cursor = RecordingCursor()

    upgrade_fingerprints(cursor)
    upgraded = "\n".join(cursor.queries)

    assert "ADD COLUMN IF NOT EXISTS checksum_algorithm TEXT" in upgraded
    assert "ADD COLUMN IF NOT EXISTS checksum TEXT" in upgraded
    assert "ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT" in upgraded
    assert "ADD COLUMN IF NOT EXISTS mime_type TEXT" in upgraded
    assert "ADD COLUMN IF NOT EXISTS checksum_calculated_at TIMESTAMPTZ" in upgraded
    assert "documents_file_fingerprint_check" in upgraded
    assert "file_size_bytes >= 0" in upgraded
    assert "checksum ~ '^[0-9a-f]{64}$'" in upgraded
    assert "documents_active_fingerprint_unique_idx" in upgraded
    assert "access_roles, checksum_algorithm, checksum, file_size_bytes" in upgraded
    assert "document_ingestion_jobs_active_document_unique_idx" in upgraded
    assert "status IN ('queued', 'running') AND request_checksum IS NOT NULL" in upgraded
    assert "request_checksum" in upgraded
    assert "force_reindex" in upgraded
    assert "CREATE TABLE IF NOT EXISTS ingestion_file_requests" in upgraded

    cursor.queries.clear()
    downgrade_fingerprints(cursor)
    downgraded = "\n".join(cursor.queries)
    assert "DROP INDEX IF EXISTS documents_active_fingerprint_unique_idx" in downgraded
    assert "DROP COLUMN IF EXISTS checksum_algorithm" in downgraded
    assert "DROP COLUMN IF EXISTS request_checksum" in downgraded
    assert "DROP TABLE IF EXISTS ingestion_file_requests" in downgraded
