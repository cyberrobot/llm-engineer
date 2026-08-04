"""Add administrator-facing knowledge sources (PR 11B)."""

from typing import Any

MIGRATION_ID = "20260803_11b_knowledge_source_management"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id TEXT PRIMARY KEY,
            assistant_id TEXT NOT NULL REFERENCES assistants(id) ON DELETE RESTRICT,
            source_type TEXT NOT NULL CHECK (source_type IN ('direct_text', 'url')),
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            retrieval_state TEXT NOT NULL CHECK (retrieval_state IN ('enabled', 'disabled')),
            direct_text TEXT,
            normalized_url TEXT,
            document_id TEXT NOT NULL,
            content_version TEXT NOT NULL CHECK (content_version ~ '^[0-9a-f]{64}$'),
            creation_idempotency_key TEXT,
            creation_request_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT knowledge_sources_payload_check CHECK (
                (source_type = 'direct_text' AND direct_text IS NOT NULL
                    AND length(trim(direct_text)) > 0 AND normalized_url IS NULL)
                OR (source_type = 'url' AND direct_text IS NULL AND normalized_url IS NOT NULL)
            ),
            CONSTRAINT knowledge_sources_document_assistant_fkey
                FOREIGN KEY (document_id, assistant_id)
                REFERENCES documents(id, assistant_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS knowledge_sources_assistant_url_unique_idx
        ON knowledge_sources(assistant_id, normalized_url)
        WHERE source_type = 'url'
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS knowledge_sources_creation_key_unique_idx
        ON knowledge_sources(creation_idempotency_key)
        WHERE creation_idempotency_key IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS knowledge_sources_assistant_page_idx
        ON knowledge_sources(assistant_id, created_at DESC, id DESC)
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP TABLE IF EXISTS knowledge_sources")
