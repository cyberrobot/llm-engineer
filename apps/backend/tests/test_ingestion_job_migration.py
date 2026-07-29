from infrastructure.database.migrations.ingestion_job_domain import downgrade, upgrade


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
    assert "ALTER COLUMN stage SET NOT NULL" in downgraded
