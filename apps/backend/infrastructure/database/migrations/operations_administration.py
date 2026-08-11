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
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'operations_runtime_state_check'
                  AND conrelid = 'operations_runtime_state'::regclass
            ) THEN
                ALTER TABLE operations_runtime_state
                DROP CONSTRAINT operations_runtime_state_check;
            END IF;
        END
        $$
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
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT operations_audit_logs_result_check
                CHECK (result IN ('STARTED', 'SUCCESS', 'FAILURE'))
        )
    """)
    cursor.execute("""
        DO $$
        DECLARE
            current_definition TEXT;
        BEGIN
            SELECT pg_get_constraintdef(oid)
            INTO current_definition
            FROM pg_constraint
            WHERE conname = 'operations_audit_logs_result_check'
              AND conrelid = 'operations_audit_logs'::regclass;

            IF current_definition IS NOT NULL
               AND position('STARTED' IN current_definition) = 0 THEN
                ALTER TABLE operations_audit_logs
                DROP CONSTRAINT operations_audit_logs_result_check;
                current_definition := NULL;
            END IF;

            IF current_definition IS NULL THEN
                ALTER TABLE operations_audit_logs
                ADD CONSTRAINT operations_audit_logs_result_check
                CHECK (result IN ('STARTED', 'SUCCESS', 'FAILURE'));
            END IF;
        END
        $$
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
