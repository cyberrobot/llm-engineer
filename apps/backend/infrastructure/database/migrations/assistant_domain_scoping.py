"""Add persistent assistants and assistant-scoped knowledge (PR 11A)."""

from typing import Any

from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, REDMOOR_ASSISTANT_SLUG

MIGRATION_ID = "20260731_11a_assistant_domain_scoping"


def upgrade(cursor: Any) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assistants (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
            visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute(
        """INSERT INTO assistants (id, slug, name, status, visibility)
           VALUES (%s, %s, 'Redmoor Assistant', 'active', 'public')
           ON CONFLICT (slug) DO NOTHING""",
        (str(REDMOOR_ASSISTANT_ID), REDMOOR_ASSISTANT_SLUG),
    )
    cursor.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS assistant_id TEXT")
    cursor.execute(
        """ALTER TABLE documents ADD COLUMN IF NOT EXISTS retrieval_state TEXT
           DEFAULT 'enabled'"""
    )
    cursor.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS assistant_id TEXT")
    cursor.execute(
        "UPDATE documents SET assistant_id = %s WHERE assistant_id IS NULL",
        (str(REDMOOR_ASSISTANT_ID),),
    )
    cursor.execute("""
        UPDATE chunks SET assistant_id = documents.assistant_id
        FROM documents
        WHERE chunks.doc_id = documents.id AND chunks.assistant_id IS NULL
    """)
    cursor.execute("UPDATE documents SET retrieval_state = 'enabled' WHERE retrieval_state IS NULL")
    cursor.execute("ALTER TABLE documents ALTER COLUMN assistant_id SET NOT NULL")
    cursor.execute("ALTER TABLE documents ALTER COLUMN retrieval_state SET NOT NULL")
    cursor.execute("ALTER TABLE chunks ALTER COLUMN assistant_id SET NOT NULL")
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE documents ADD CONSTRAINT documents_assistant_id_fkey
                FOREIGN KEY (assistant_id) REFERENCES assistants(id) ON DELETE RESTRICT;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE documents ADD CONSTRAINT documents_retrieval_state_check
                CHECK (retrieval_state IN ('enabled', 'disabled'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE documents ADD CONSTRAINT documents_id_assistant_unique
                UNIQUE (id, assistant_id);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE chunks ADD CONSTRAINT chunks_assistant_id_fkey
                FOREIGN KEY (assistant_id) REFERENCES assistants(id) ON DELETE RESTRICT;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE chunks ADD CONSTRAINT chunks_document_assistant_fkey
                FOREIGN KEY (doc_id, assistant_id) REFERENCES documents(id, assistant_id)
                ON DELETE CASCADE;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    cursor.execute("DROP INDEX IF EXISTS documents_source_url_unique_idx")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS documents_assistant_source_url_unique_idx
        ON documents(assistant_id, source_url) WHERE source_url IS NOT NULL
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS documents_assistant_id_idx ON documents(assistant_id)"
    )
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS documents_assistant_retrieval_state_idx
        ON documents(assistant_id, retrieval_state)
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS chunks_assistant_id_idx ON chunks(assistant_id)")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS chunks_assistant_document_idx
        ON chunks(assistant_id, doc_id)
    """)


def downgrade(cursor: Any) -> None:
    cursor.execute("DROP INDEX IF EXISTS chunks_assistant_document_idx")
    cursor.execute("DROP INDEX IF EXISTS chunks_assistant_id_idx")
    cursor.execute("DROP INDEX IF EXISTS documents_assistant_retrieval_state_idx")
    cursor.execute("DROP INDEX IF EXISTS documents_assistant_id_idx")
    cursor.execute("DROP INDEX IF EXISTS documents_assistant_source_url_unique_idx")
    cursor.execute("ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_document_assistant_fkey")
    cursor.execute("ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_assistant_id_fkey")
    cursor.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_id_assistant_unique")
    cursor.execute(
        "ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_retrieval_state_check"
    )
    cursor.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_assistant_id_fkey")
    cursor.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS assistant_id")
    cursor.execute("ALTER TABLE documents DROP COLUMN IF EXISTS retrieval_state")
    cursor.execute("ALTER TABLE documents DROP COLUMN IF EXISTS assistant_id")
    cursor.execute("DROP TABLE IF EXISTS assistants")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS documents_source_url_unique_idx
        ON documents(source_url) WHERE source_url IS NOT NULL
    """)
