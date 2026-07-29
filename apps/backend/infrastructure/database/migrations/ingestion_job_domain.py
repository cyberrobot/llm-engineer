"""Add the persistent document ingestion-job domain (PR 9A)."""

from typing import Any

MIGRATION_ID = "20260729_9a_ingestion_job_domain"


def upgrade(cursor: Any) -> None:
    cursor.execute("ALTER TABLE document_ingestion_jobs ALTER COLUMN stage DROP NOT NULL")
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            ADD COLUMN IF NOT EXISTS current_step TEXT,
            ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS failure_code TEXT,
            ADD COLUMN IF NOT EXISTS failure_message TEXT,
            ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET current_step = stage
        WHERE current_step IS NULL AND stage IN ('parse', 'chunk', 'embed', 'persist')
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET failure_message = error
        WHERE failure_message IS NULL AND error IS NOT NULL
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET started_at = COALESCE(started_at, created_at)
        WHERE status IN ('running', 'completed', 'failed')
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET completed_at = COALESCE(completed_at, updated_at)
        WHERE status IN ('completed', 'failed', 'cancelled')
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET failure_code = NULL, failure_message = NULL
        WHERE status <> 'failed'
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET failure_code = COALESCE(failure_code, 'legacy_ingestion_failure')
        WHERE status = 'failed'
          AND NULLIF(trim(COALESCE(failure_message, '')), '') IS NULL
    """)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_status_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_status_check
                CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_step_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_step_check
                CHECK (current_step IS NULL OR current_step IN ('parse', 'chunk', 'embed', 'persist'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_retry_count_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_retry_count_check
                CHECK (retry_count >= 0);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_lifecycle_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_lifecycle_check CHECK (
                    (status = 'queued' AND started_at IS NULL AND completed_at IS NULL
                        AND failure_code IS NULL AND failure_message IS NULL)
                    OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL
                        AND failure_code IS NULL AND failure_message IS NULL)
                    OR (status = 'completed' AND started_at IS NOT NULL
                        AND completed_at IS NOT NULL AND failure_code IS NULL
                        AND failure_message IS NULL)
                    OR (status = 'failed' AND started_at IS NOT NULL
                        AND completed_at IS NOT NULL
                        AND (failure_code IS NOT NULL OR failure_message IS NOT NULL))
                    OR (status = 'cancelled' AND completed_at IS NOT NULL
                        AND failure_code IS NULL AND failure_message IS NULL)
                );
            END IF;
        END
        $$
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS document_ingestion_jobs_idempotency_key_unique_idx
        ON document_ingestion_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_status_idx
        ON document_ingestion_jobs(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_created_at_idx
        ON document_ingestion_jobs(created_at DESC)
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_created_at_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_status_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_idempotency_key_unique_idx")
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_lifecycle_check,
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_retry_count_check,
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_step_check,
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_status_check
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET stage = COALESCE(stage, current_step, 'validate')
    """)
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            ALTER COLUMN stage SET NOT NULL,
            DROP COLUMN IF EXISTS completed_at,
            DROP COLUMN IF EXISTS started_at,
            DROP COLUMN IF EXISTS idempotency_key,
            DROP COLUMN IF EXISTS failure_message,
            DROP COLUMN IF EXISTS failure_code,
            DROP COLUMN IF EXISTS retry_count,
            DROP COLUMN IF EXISTS current_step
    """)
