"""Add durable, indexed administrative action audit records (PR 10C)."""

from typing import Any

MIGRATION_ID = "20260811_10c_operations_administration"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations_runtime_state (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
            maintenance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            maintenance_message TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT
        )
    """)
    cursor.execute("""
        ALTER TABLE operations_runtime_state
        DROP CONSTRAINT IF EXISTS operations_runtime_state_check
    """)
    cursor.execute("""
        INSERT INTO operations_runtime_state (singleton)
        VALUES (TRUE) ON CONFLICT (singleton) DO NOTHING
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations_audit_logs (
            id UUID PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            resource TEXT NOT NULL,
            result TEXT NOT NULL,
            request_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            duration_ms BIGINT NOT NULL CHECK (duration_ms >= 0),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    cursor.execute("""
        ALTER TABLE operations_audit_logs
        DROP CONSTRAINT IF EXISTS operations_audit_logs_result_check
    """)
    cursor.execute("""
        ALTER TABLE operations_audit_logs
        ADD CONSTRAINT operations_audit_logs_result_check
        CHECK (result IN ('STARTED', 'SUCCESS', 'FAILURE'))
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS operations_audit_logs_timestamp_idx
        ON operations_audit_logs(timestamp DESC, id DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS operations_audit_logs_actor_timestamp_idx
        ON operations_audit_logs(actor, timestamp DESC, id DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS operations_audit_logs_action_timestamp_idx
        ON operations_audit_logs(action, timestamp DESC, id DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS operations_audit_logs_resource_timestamp_idx
        ON operations_audit_logs(resource, timestamp DESC, id DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS operations_audit_logs_result_timestamp_idx
        ON operations_audit_logs(result, timestamp DESC, id DESC)
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS operations_audit_logs")
    cursor.execute("DROP TABLE IF EXISTS operations_runtime_state")
