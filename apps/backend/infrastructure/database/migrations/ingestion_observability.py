"""Add durable ingestion step-attempt history and observability query indexes (PR 9G)."""

from typing import Any

MIGRATION_ID = "20260731_9g_ingestion_observability"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_step_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ingestion_job_id TEXT NOT NULL
                REFERENCES document_ingestion_jobs(id) ON DELETE CASCADE,
            step TEXT NOT NULL CHECK (step IN ('parse', 'chunk', 'embed', 'persist')),
            attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
            status TEXT NOT NULL
                CHECK (status IN ('running', 'completed', 'failed', 'interrupted')),
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            duration_ms BIGINT CHECK (duration_ms >= 0),
            failure_code TEXT,
            retryable BOOLEAN,
            worker_id TEXT,
            claim_version BIGINT CHECK (claim_version IS NULL OR claim_version >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (ingestion_job_id, step, attempt_number),
            CHECK (
                (status = 'running' AND completed_at IS NULL AND duration_ms IS NULL)
                OR (status = 'interrupted' AND completed_at IS NULL)
                OR (status IN ('completed', 'failed') AND completed_at IS NOT NULL
                    AND duration_ms IS NOT NULL)
            )
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ingestion_step_executions_job_started_idx
        ON ingestion_step_executions(ingestion_job_id, started_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ingestion_step_executions_status_started_idx
        ON ingestion_step_executions(status, started_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_status_created_idx
        ON document_ingestion_jobs(status, created_at DESC, id DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_document_created_idx
        ON document_ingestion_jobs(document_id, created_at DESC, id DESC)
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_document_created_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_status_created_idx")
    cursor.execute("DROP INDEX IF EXISTS ingestion_step_executions_status_started_idx")
    cursor.execute("DROP INDEX IF EXISTS ingestion_step_executions_job_started_idx")
    cursor.execute("DROP TABLE IF EXISTS ingestion_step_executions")
