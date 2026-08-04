import psycopg

from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS, get_database_settings
from infrastructure.database.migrations.administrator_authentication import (
    upgrade as upgrade_administrator_authentication,
)
from infrastructure.database.migrations.assistant_domain_scoping import (
    upgrade as upgrade_assistant_domain_scoping,
)
from infrastructure.database.migrations.background_worker_execution import (
    upgrade as upgrade_background_worker_execution,
)
from infrastructure.database.migrations.file_integrity_deduplication import (
    upgrade as upgrade_file_integrity_deduplication,
)
from infrastructure.database.migrations.ingestion_job_domain import (
    upgrade as upgrade_ingestion_job_domain,
)
from infrastructure.database.migrations.ingestion_observability import (
    upgrade as upgrade_ingestion_observability,
)
from infrastructure.database.migrations.ingestion_operational_maintenance import (
    upgrade as upgrade_ingestion_operational_maintenance,
)
from infrastructure.database.migrations.ingestion_pipeline_checkpoint import (
    upgrade as upgrade_ingestion_pipeline_checkpoint,
)
from infrastructure.database.migrations.ingestion_retry_recovery import (
    upgrade as upgrade_ingestion_retry_recovery,
)
from infrastructure.database.migrations.knowledge_source_management import (
    upgrade as upgrade_knowledge_source_management,
)
from infrastructure.database.migrations.transactional_ingestion_persistence import (
    upgrade as upgrade_transactional_ingestion_persistence,
)


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in the environment variables.")
    settings = get_database_settings()
    statement_timeout_ms = int(settings.operation_timeout_seconds * 1_000)
    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=settings.connect_timeout_seconds,
        options=f"-c statement_timeout={statement_timeout_ms}",
    )


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            upgrade_administrator_authentication(cur)
            cur.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'ingestion_jobs'
                          AND column_name = 'document_id'
                    ) AND to_regclass('document_ingestion_jobs') IS NULL THEN
                        ALTER TABLE ingestion_jobs RENAME TO document_ingestion_jobs;
                        ALTER INDEX IF EXISTS ingestion_jobs_document_id_idx
                            RENAME TO document_ingestion_jobs_document_id_idx;
                    END IF;
                END
                $$
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    doc_type TEXT NOT NULL,
                    access_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'indexed',
                    upload_path TEXT,
                    original_filename TEXT,
                    source_url TEXT,
                    title TEXT,
                    content_hash TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'running', 'completed', 'failed')
                    ),
                    documents_discovered INTEGER NOT NULL DEFAULT 0 CHECK (
                        documents_discovered >= 0
                    ),
                    documents_processed INTEGER NOT NULL DEFAULT 0 CHECK (
                        documents_processed >= 0
                        AND documents_processed <= documents_discovered
                    ),
                    chunks_created INTEGER NOT NULL DEFAULT 0 CHECK (chunks_created >= 0),
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    CHECK (
                        (status = 'pending' AND started_at IS NULL
                            AND completed_at IS NULL AND error_message IS NULL)
                        OR (status = 'running' AND started_at IS NOT NULL
                            AND completed_at IS NULL AND error_message IS NULL)
                        OR (status = 'completed' AND started_at IS NOT NULL
                            AND completed_at IS NOT NULL AND error_message IS NULL)
                        OR (status = 'failed' AND completed_at IS NOT NULL
                            AND length(trim(error_message)) > 0)
                    )
                )
            """)
            upgrade_ingestion_job_domain(cur)
            upgrade_ingestion_pipeline_checkpoint(cur)
            upgrade_ingestion_retry_recovery(cur)
            upgrade_file_integrity_deduplication(cur)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    embedding VECTOR({EMBEDDING_VECTOR_DIMENSIONS}) NOT NULL,
                    access_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    text_search TSVECTOR,
                    sequence INTEGER,
                    content_hash TEXT,
                    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            upgrade_assistant_domain_scoping(cur)
            upgrade_knowledge_source_management(cur)
            upgrade_transactional_ingestion_persistence(cur)
            upgrade_background_worker_execution(cur)
            upgrade_ingestion_observability(cur)
            upgrade_ingestion_operational_maintenance(cur)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id BIGSERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    user_role TEXT NOT NULL,
                    question TEXT NOT NULL,
                    queries JSONB NOT NULL DEFAULT '[]'::jsonb,
                    reply JSONB NOT NULL DEFAULT '{}'::jsonb,
                    retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
                    reranked_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
                    evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
                    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chunks_text_search_idx
                ON chunks USING GIN(text_search)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
                ON chunks
                USING hnsw (embedding vector_cosine_ops);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS chunks_access_roles_idx
                ON chunks
                USING GIN (access_roles);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS audit_logs_timestamp_idx
                ON audit_logs(timestamp DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS document_ingestion_jobs_document_id_idx
                ON document_ingestion_jobs(document_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ingestion_jobs_created_at_idx
                ON ingestion_jobs(created_at DESC)
            """)
            cur.execute("""
                CREATE OR REPLACE FUNCTION chunks_text_search_trigger()
                RETURNS trigger AS $$
                BEGIN
                    NEW.text_search := to_tsvector('english', NEW.text);
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql
            """)
            cur.execute("""
                DROP TRIGGER IF EXISTS chunks_text_search_update ON chunks;
                CREATE TRIGGER chunks_text_search_update
                BEFORE INSERT OR UPDATE ON chunks
                FOR EACH ROW
                EXECUTE FUNCTION chunks_text_search_trigger();
            """)
            cur.execute("""
                ALTER TABLE audit_logs
                ADD COLUMN IF NOT EXISTS reranked_chunks JSONB NOT NULL DEFAULT '[]'::jsonb
            """)
            cur.execute("""
                ALTER TABLE audit_logs
                ADD COLUMN IF NOT EXISTS evaluation JSONB NOT NULL DEFAULT '{}'::jsonb
            """)
            cur.execute("""
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'indexed'
            """)
            cur.execute("""
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS upload_path TEXT
            """)
            cur.execute("""
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS original_filename TEXT
            """)
            cur.execute("""
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """)
            cur.execute("""
                ALTER TABLE documents
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """)
            cur.execute("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url TEXT
            """)
            cur.execute("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS title TEXT
            """)
            cur.execute("""
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT
            """)
            cur.execute("""
                ALTER TABLE chunks ADD COLUMN IF NOT EXISTS sequence INTEGER
            """)
            cur.execute("""
                ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash TEXT
            """)
            cur.execute("""
                ALTER TABLE chunks
                ADD COLUMN IF NOT EXISTS heading_path JSONB NOT NULL DEFAULT '[]'::jsonb
            """)
            cur.execute("""
                ALTER TABLE chunks
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """)
            cur.execute("""
                ALTER TABLE chunks
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS chunks_document_sequence_unique_idx
                ON chunks(doc_id, sequence) WHERE sequence IS NOT NULL
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS chunks_document_content_hash_unique_idx
                ON chunks(doc_id, content_hash) WHERE content_hash IS NOT NULL
            """)
