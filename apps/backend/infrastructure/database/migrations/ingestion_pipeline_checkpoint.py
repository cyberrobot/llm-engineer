"""Add a durable last-completed-step checkpoint for ingestion orchestration (PR 9B)."""

from typing import Any

MIGRATION_ID = "20260729_9b_ingestion_pipeline_checkpoint"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
        ADD COLUMN IF NOT EXISTS last_completed_step TEXT
    """)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_completed_step_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_completed_step_check
                CHECK (
                    last_completed_step IS NULL
                    OR last_completed_step IN ('parse', 'chunk', 'embed', 'persist')
                );
            END IF;
        END
        $$
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_completed_step_check,
            DROP COLUMN IF EXISTS last_completed_step
    """)
