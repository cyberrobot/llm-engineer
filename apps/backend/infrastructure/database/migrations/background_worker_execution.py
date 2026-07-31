"""Add leased background-worker ownership and fencing metadata (PR 9F)."""

from typing import Any

MIGRATION_ID = "20260731_9f_background_worker_execution"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            ADD COLUMN IF NOT EXISTS worker_id TEXT,
            ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS claim_version BIGINT NOT NULL DEFAULT 0
    """)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_claim_version_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_claim_version_check
                CHECK (claim_version >= 0);
            END IF;
        END
        $$
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_worker_queue_idx
        ON document_ingestion_jobs(status, created_at, id)
        WHERE status = 'queued'
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_expired_lease_idx
        ON document_ingestion_jobs(status, lease_expires_at)
        WHERE status = 'running'
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_expired_lease_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_worker_queue_idx")
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_claim_version_check,
            DROP COLUMN IF EXISTS claim_version,
            DROP COLUMN IF EXISTS last_heartbeat_at,
            DROP COLUMN IF EXISTS lease_expires_at,
            DROP COLUMN IF EXISTS claimed_at,
            DROP COLUMN IF EXISTS worker_id
    """)
