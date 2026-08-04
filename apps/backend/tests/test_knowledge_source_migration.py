from infrastructure.database.migrations.knowledge_source_management import downgrade, upgrade


class RecordingCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query, _parameters=None):
        self.queries.append(query)


def test_knowledge_source_migration_is_scoped_constrained_and_reversible():
    cursor = RecordingCursor()
    upgrade(cursor)
    sql = "\n".join(cursor.queries)
    assert "knowledge_sources_payload_check" in sql
    assert "knowledge_sources_document_assistant_fkey" in sql
    assert "knowledge_sources_assistant_url_unique_idx" in sql
    downgrade(cursor)
    assert "DROP TABLE IF EXISTS knowledge_sources" in cursor.queries[-1]
