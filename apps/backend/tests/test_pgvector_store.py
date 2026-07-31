from unittest.mock import MagicMock

from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.infrastructure.vector_store import PgVectorStore


def test_pgvector_store_uses_parameterized_similarity_search():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("chunk-1", "doc-1", "Guide", "Relevant text", 0.92, "/guide.pdf")
    ]
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor

    records = PgVectorStore(lambda: connection).similarity_search(
        [0.1, 0.2],
        assistant_id=REDMOOR_ASSISTANT_ID,
        limit=3,
        min_score=0.7,
    )

    parameters = cursor.execute.call_args.args[1]
    assert parameters == (
        [0.1, 0.2],
        str(REDMOOR_ASSISTANT_ID),
        str(REDMOOR_ASSISTANT_ID),
        [0.1, 0.2],
        0.7,
        [0.1, 0.2],
        3,
    )
    assert records[0].chunk_id == "chunk-1"
    assert records[0].score == 0.92
