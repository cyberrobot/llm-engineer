"""Add durable, replay-safe evidence for transactional ingestion persistence (PR 9E)."""

from typing import Any

MIGRATION_ID = "20260730_9e_transactional_ingestion_persistence"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS last_ingestion_job_id TEXT
            REFERENCES document_ingestion_jobs(id) ON DELETE RESTRICT
    """)
    cursor.execute("""
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS ingestion_job_id TEXT
            REFERENCES document_ingestion_jobs(id) ON DELETE RESTRICT
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_persistence_results (
            ingestion_job_id TEXT PRIMARY KEY
                REFERENCES document_ingestion_jobs(id) ON DELETE RESTRICT,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
            command_hash TEXT NOT NULL CHECK (command_hash ~ '^[0-9a-f]{64}$'),
            persistence_mode TEXT NOT NULL CHECK (
                persistence_mode IN ('NEW', 'REINDEX', 'RECOVERY')
            ),
            source_fingerprint TEXT CHECK (
                source_fingerprint IS NULL OR source_fingerprint ~ '^[0-9a-f]{64}$'
            ),
            result JSONB NOT NULL CHECK (jsonb_typeof(result) = 'object'),
            committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS chunks_ingestion_job_id_idx
        ON chunks(ingestion_job_id) WHERE ingestion_job_id IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS documents_last_ingestion_job_id_idx
        ON documents(last_ingestion_job_id) WHERE last_ingestion_job_id IS NOT NULL
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS documents_last_ingestion_job_id_idx")
    cursor.execute("DROP INDEX IF EXISTS chunks_ingestion_job_id_idx")
    cursor.execute("DROP TABLE IF EXISTS ingestion_persistence_results")
    cursor.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS ingestion_job_id")
    cursor.execute("ALTER TABLE documents DROP COLUMN IF EXISTS last_ingestion_job_id")
