"""Add exact source-file integrity metadata and ingestion deduplication safeguards (PR 9D)."""

from typing import Any

MIGRATION_ID = "20260730_9d_file_integrity_deduplication"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS checksum_algorithm TEXT,
            ADD COLUMN IF NOT EXISTS checksum TEXT,
            ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT,
            ADD COLUMN IF NOT EXISTS mime_type TEXT,
            ADD COLUMN IF NOT EXISTS checksum_calculated_at TIMESTAMPTZ
    """)
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            ADD COLUMN IF NOT EXISTS request_checksum TEXT,
            ADD COLUMN IF NOT EXISTS force_reindex BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS trigger_reason TEXT
    """)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'documents_file_fingerprint_check'
                  AND conrelid = 'documents'::regclass
            ) THEN
                ALTER TABLE documents ADD CONSTRAINT documents_file_fingerprint_check CHECK (
                    (checksum_algorithm IS NULL AND checksum IS NULL
                        AND file_size_bytes IS NULL AND checksum_calculated_at IS NULL)
                    OR (checksum_algorithm = 'sha256'
                        AND checksum ~ '^[0-9a-f]{64}$'
                        AND file_size_bytes >= 0
                        AND checksum_calculated_at IS NOT NULL)
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_file_request_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_file_request_check CHECK (
                    request_checksum IS NULL
                    OR request_checksum ~ '^[0-9a-f]{64}$'
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'document_ingestion_jobs_trigger_reason_check'
                  AND conrelid = 'document_ingestion_jobs'::regclass
            ) THEN
                ALTER TABLE document_ingestion_jobs
                ADD CONSTRAINT document_ingestion_jobs_trigger_reason_check CHECK (
                    trigger_reason IS NULL OR trigger_reason IN (
                        'NEW_CONTENT', 'MODIFIED_CONTENT', 'FAILED_RECOVERY', 'FORCED_REINDEX'
                    )
                );
            END IF;
        END
        $$
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS documents_active_fingerprint_unique_idx
        ON documents(access_roles, checksum_algorithm, checksum, file_size_bytes)
        WHERE checksum IS NOT NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS document_ingestion_jobs_active_document_unique_idx
        ON document_ingestion_jobs(document_id)
        WHERE status IN ('queued', 'running') AND request_checksum IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS documents_file_fingerprint_lookup_idx
        ON documents(checksum_algorithm, checksum, file_size_bytes)
        WHERE checksum IS NOT NULL
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_file_requests (
            idempotency_key TEXT PRIMARY KEY,
            request_checksum TEXT NOT NULL CHECK (request_checksum ~ '^[0-9a-f]{64}$'),
            force_reindex BOOLEAN NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            ingestion_job_id TEXT NOT NULL REFERENCES document_ingestion_jobs(id) ON DELETE CASCADE,
            content_status TEXT NOT NULL CHECK (content_status IN (
                'NEW_CONTENT', 'DUPLICATE_CONTENT', 'MODIFIED_CONTENT', 'FORCED_REINDEX'
            )),
            deduplicated BOOLEAN NOT NULL,
            ingestion_required BOOLEAN NOT NULL,
            ingestion_in_progress BOOLEAN NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS ingestion_file_requests")
    cursor.execute("DROP INDEX IF EXISTS documents_file_fingerprint_lookup_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_active_document_unique_idx")
    cursor.execute("DROP INDEX IF EXISTS documents_active_fingerprint_unique_idx")
    cursor.execute("""
        ALTER TABLE document_ingestion_jobs
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_trigger_reason_check,
            DROP CONSTRAINT IF EXISTS document_ingestion_jobs_file_request_check,
            DROP COLUMN IF EXISTS trigger_reason,
            DROP COLUMN IF EXISTS force_reindex,
            DROP COLUMN IF EXISTS request_checksum
    """)
    cursor.execute("""
        ALTER TABLE documents
            DROP CONSTRAINT IF EXISTS documents_file_fingerprint_check,
            DROP COLUMN IF EXISTS checksum_calculated_at,
            DROP COLUMN IF EXISTS mime_type,
            DROP COLUMN IF EXISTS file_size_bytes,
            DROP COLUMN IF EXISTS checksum,
            DROP COLUMN IF EXISTS checksum_algorithm
    """)
