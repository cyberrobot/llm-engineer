from infrastructure.database.migrations.background_worker_execution import downgrade, upgrade


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(" ".join(query.split()))


def test_worker_migration_adds_fenced_lease_fields_and_claim_indexes():
    cursor = RecordingCursor()

    upgrade(cursor)
    sql = "\n".join(cursor.queries)

    assert "ADD COLUMN IF NOT EXISTS worker_id TEXT" in sql
    assert "ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS claim_version BIGINT NOT NULL DEFAULT 0" in sql
    assert "CHECK (claim_version >= 0)" in sql
    assert "status, created_at, id" in sql
    assert "status, lease_expires_at" in sql

    cursor.queries.clear()
    downgrade(cursor)
    downgraded = "\n".join(cursor.queries)
    assert "DROP COLUMN IF EXISTS worker_id" in downgraded
    assert "DROP COLUMN IF EXISTS claim_version" in downgraded
