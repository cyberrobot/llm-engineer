"""Add bounded candidate-query indexes for ingestion maintenance (PR 9H)."""

from typing import Any

MIGRATION_ID = "20260731_9h_ingestion_operational_maintenance"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS document_ingestion_jobs_terminal_retention_idx
        ON document_ingestion_jobs(status, completed_at, id)
        WHERE status IN ('completed', 'failed', 'cancelled')
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ingestion_step_executions_retention_idx
        ON ingestion_step_executions(completed_at, id)
        WHERE status IN ('completed', 'failed')
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS documents_upload_path_idx
        ON documents(upload_path)
        WHERE upload_path IS NOT NULL
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS documents_upload_path_idx")
    cursor.execute("DROP INDEX IF EXISTS ingestion_step_executions_retention_idx")
    cursor.execute("DROP INDEX IF EXISTS document_ingestion_jobs_terminal_retention_idx")
