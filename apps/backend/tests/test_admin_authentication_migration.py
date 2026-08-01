from infrastructure.database.migrations.administrator_authentication import downgrade, upgrade


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(" ".join(query.split()))


def test_authentication_migration_defines_constrained_accounts_hashed_sessions_and_indexes():
    cursor = RecordingCursor()
    upgrade(cursor)
    sql = "\n".join(cursor.queries)

    assert "CREATE TABLE IF NOT EXISTS administrators" in sql
    assert "email TEXT NOT NULL UNIQUE" in sql
    assert "email = lower(btrim(email))" in sql
    assert "role IN ('administrator')" in sql
    assert "status IN ('active', 'disabled')" in sql
    assert "CREATE TABLE IF NOT EXISTS administrator_sessions" in sql
    assert "token_hash TEXT NOT NULL UNIQUE" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "administrator_sessions_expires_at_idx" in sql
    assert "WHERE revoked_at IS NULL" in sql

    cursor.queries.clear()
    downgrade(cursor)
    assert cursor.queries == [
        "DROP TABLE IF EXISTS administrator_sessions",
        "DROP TABLE IF EXISTS administrators",
    ]
