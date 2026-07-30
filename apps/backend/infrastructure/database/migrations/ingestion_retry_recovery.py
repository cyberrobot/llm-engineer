"""Persist current-step retry recovery state for ingestion orchestration (PR 9C)."""

from typing import Any

MIGRATION_ID = "20260729_9c_ingestion_retry_recovery"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            ADD COLUMN IF NOT EXISTS current_step_attempt_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ
    """)
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
        DROP CONSTRAINT IF EXISTS document_ingestion_jobs_lifecycle_check
    """)
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
        ADD CONSTRAINT document_ingestion_jobs_lifecycle_check CHECK (
            (status = 'queued' AND started_at IS NULL AND completed_at IS NULL
                AND failure_code IS NULL AND failure_message IS NULL)
            OR (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL
                AND (
                    (failure_code IS NULL AND failure_message IS NULL)
                    OR current_step_attempt_count > 0
                ))
            OR (status = 'completed' AND started_at IS NOT NULL
                AND completed_at IS NOT NULL AND failure_code IS NULL
                AND failure_message IS NULL)
            OR (status = 'failed' AND started_at IS NOT NULL
                AND completed_at IS NOT NULL
                AND (failure_code IS NOT NULL OR failure_message IS NOT NULL))
            OR (status = 'cancelled' AND completed_at IS NOT NULL
                AND failure_code IS NULL AND failure_message IS NULL)
        )
    """)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_attempt_count_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_attempt_count_check
                CHECK (current_step_attempt_count >= 0);
            END IF;
        END
        $$
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
        DROP CONSTRAINT IF EXISTS document_ingestion_jobs_lifecycle_check
    """)
    cursor.execute("""
        UPDATE document_ingestion_jobs
        SET failure_code = NULL, failure_message = NULL
        WHERE status = 'running'
    """)
    cursor.execute("""
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
        )
    """)
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_attempt_count_check,
            DROP COLUMN IF EXISTS current_step_attempt_count,
            DROP COLUMN IF EXISTS last_attempted_at
    """)
