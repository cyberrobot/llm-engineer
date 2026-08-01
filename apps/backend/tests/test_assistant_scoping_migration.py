from infrastructure.database.migrations.assistant_domain_scoping import downgrade, upgrade


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str, _parameters=None) -> None:
        self.queries.append(" ".join(query.split()))


def test_migration_bootstraps_and_backfills_assistant_scoped_knowledge_safely():
    cursor = RecordingCursor()

    upgrade(cursor)

    sql = "\n".join(cursor.queries)
    assert "CREATE TABLE IF NOT EXISTS assistants" in sql
    assert "ON CONFLICT (slug) DO NOTHING" in sql
    assert sql.index("UPDATE documents SET assistant_id") < sql.index(
        "ALTER TABLE documents ALTER COLUMN assistant_id SET NOT NULL"
    )
    assert sql.index("UPDATE chunks SET assistant_id") < sql.index(
        "ALTER TABLE chunks ALTER COLUMN assistant_id SET NOT NULL"
    )
    assert "documents_retrieval_state_check" in sql
    assert "chunks_document_assistant_fkey" in sql
    assert "duplicate_object OR duplicate_table" in sql
    assert "ON DELETE CASCADE" in sql
    assert "documents_assistant_source_url_unique_idx" in sql
    assert "documents_assistant_retrieval_state_idx" in sql
    assert "chunks_assistant_document_idx" in sql

    downgrade(cursor)
    assert "DROP TABLE IF EXISTS assistants" in "\n".join(cursor.queries)
