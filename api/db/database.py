import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in the environment variables.")
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    doc_type TEXT NOT NULL,
                    access_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'indexed',
                    upload_path TEXT,
                    original_filename TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
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
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    embedding VECTOR(1536) NOT NULL,
                    access_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                    text_search TSVECTOR
                )
            """)
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
                CREATE INDEX IF NOT EXISTS ingestion_jobs_document_id_idx
                ON ingestion_jobs(document_id)
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
