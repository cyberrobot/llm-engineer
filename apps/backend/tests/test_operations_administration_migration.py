from infrastructure.database.migrations.operations_administration import downgrade, upgrade


class Cursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(" ".join(statement.split()))


def test_operations_audit_migration_is_reversible_and_indexed_for_supported_filters():
    cursor = Cursor()
    upgrade(cursor)
    sql = " ".join(cursor.statements)

    assert "CREATE TABLE IF NOT EXISTS operations_audit_logs" in sql
    assert "CREATE TABLE IF NOT EXISTS operations_runtime_state" in sql
    assert "metadata JSONB NOT NULL" in sql
    assert "CHECK (result IN ('STARTED', 'SUCCESS', 'FAILURE'))" in sql
    assert "DROP CONSTRAINT IF EXISTS operations_runtime_state_check" in sql
    assert "operations_audit_logs_timestamp_idx" in sql
    assert "operations_audit_logs_actor_timestamp_idx" in sql
    assert "operations_audit_logs_action_timestamp_idx" in sql
    assert "operations_audit_logs_resource_timestamp_idx" in sql
    assert "operations_audit_logs_result_timestamp_idx" in sql

    downgrade(cursor)
    assert cursor.statements[-2:] == [
        "DROP TABLE IF EXISTS operations_audit_logs",
        "DROP TABLE IF EXISTS operations_runtime_state",
    ]
