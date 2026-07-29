from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from uuid import NAMESPACE_URL, uuid4, uuid5

import psycopg
import pytest

from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.knowledge_persistence import KnowledgeDocumentRecord, PersistedKnowledgeChunk
from assistant.infrastructure.repositories.knowledge_persistence import (
    PostgresKnowledgePersistenceRepository,
)
from assistant.infrastructure.vector_store.pgvector import PgVectorStore
from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS
from infrastructure.database.connection import get_connection, init_db


class DeterministicEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1) for _ in texts]


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def processed(source_url: str, *, version: str, texts: list[str]) -> ContentProcessingResult:
    chunks = [
        KnowledgeChunk(
            id=uuid5(NAMESPACE_URL, f"{source_url}\0{version}\0{index}"),
            source_url=source_url,
            title="Persistence integration guide",
            sequence=index,
            text=text,
            content_hash=f"{version}-chunk-{index}",
            document_content_hash=version,
            heading_path=("Integration",),
            character_count=len(text),
        )
        for index, text in enumerate(texts)
    ]
    return ContentProcessingResult(
        documents_received=1,
        documents_processed=1,
        documents_skipped=0,
        chunks_created=len(chunks),
        chunks=chunks,
        warnings=[],
        duration_ms=1,
    )


def delete_document(source_url: str) -> None:
    with suppress(Exception), get_connection() as connection:
        connection.execute("DELETE FROM documents WHERE source_url = %s", (source_url,))


def test_processed_knowledge_is_idempotent_retrievable_and_replaces_stale_chunks():
    require_database()
    init_db()
    source_url = f"https://example.com/integration-{uuid4()}"
    repository = PostgresKnowledgePersistenceRepository()
    provider = DeterministicEmbeddingProvider()
    service = KnowledgePersistenceService(
        provider,
        repository,
        embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        embedding_batch_size=100,
    )

    try:
        initial = service.persist(
            processed(source_url, version="v1", texts=["Current persistence knowledge"]),
            access_roles=("user",),
        )
        repeated = service.persist(
            processed(source_url, version="v1", texts=["Current persistence knowledge"]),
            access_roles=("user",),
        )
        roles_changed = service.persist(
            processed(source_url, version="v1", texts=["Current persistence knowledge"]),
            access_roles=("manager",),
        )

        records = PgVectorStore().similarity_search(
            [1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1),
            limit=50,
            min_score=0.99,
        )
        matching = [record for record in records if record.source_uri == source_url]
        with get_connection() as connection:
            document_count = connection.execute(
                "SELECT count(*) FROM documents WHERE source_url = %s", (source_url,)
            ).fetchone()[0]
            chunk_roles = connection.execute(
                """
                SELECT chunks.access_roles
                FROM chunks JOIN documents ON documents.id = chunks.doc_id
                WHERE documents.source_url = %s
                """,
                (source_url,),
            ).fetchone()[0]

        assert initial.documents_created == 1
        assert repeated.documents_unchanged == 1
        assert repeated.embeddings_generated == 0
        assert roles_changed.documents_updated == 1
        assert roles_changed.chunks_updated == 1
        assert roles_changed.embeddings_generated == 0
        assert provider.calls == 1
        assert document_count == 1
        assert chunk_roles == ["manager"]
        assert len(matching) == 1
        assert matching[0].content == "Current persistence knowledge"
        assert matching[0].document_title == "Persistence integration guide"

        changed = service.persist(
            processed(source_url, version="v2", texts=["Replacement persistence knowledge"]),
            access_roles=("manager",),
        )
        with get_connection() as connection:
            stored_texts = connection.execute(
                """
                SELECT chunks.text
                FROM chunks JOIN documents ON documents.id = chunks.doc_id
                WHERE documents.source_url = %s
                ORDER BY chunks.sequence
                """,
                (source_url,),
            ).fetchall()

        assert changed.documents_updated == 1
        assert changed.chunks_removed == 1
        assert stored_texts == [("Replacement persistence knowledge",)]
    finally:
        delete_document(source_url)


def test_repository_rolls_back_document_when_chunk_insert_fails():
    require_database()
    init_db()
    source_url = f"https://example.com/rollback-{uuid4()}"
    repository = PostgresKnowledgePersistenceRepository()
    document = KnowledgeDocumentRecord(
        id=str(uuid4()),
        source_url=source_url,
        title="Rollback guide",
        content_hash="rollback-v1",
        access_roles=("user",),
    )
    duplicate_id = str(uuid4())
    chunks = [
        PersistedKnowledgeChunk(
            id=duplicate_id,
            document_id=document.id,
            sequence=index,
            text=f"Chunk {index}",
            content_hash=f"rollback-chunk-{index}",
            embedding=tuple([1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1)),
            heading_path=(),
            access_roles=("user",),
        )
        for index in range(2)
    ]

    try:
        with pytest.raises(psycopg.errors.UniqueViolation):
            repository.replace_document(document, chunks)

        with get_connection() as connection:
            document_count = connection.execute(
                "SELECT count(*) FROM documents WHERE source_url = %s", (source_url,)
            ).fetchone()[0]
            chunk_count = connection.execute(
                "SELECT count(*) FROM chunks WHERE doc_id = %s", (document.id,)
            ).fetchone()[0]

        assert document_count == 0
        assert chunk_count == 0
    finally:
        delete_document(source_url)


def test_concurrent_duplicate_writes_leave_one_document_and_one_chunk():
    require_database()
    init_db()
    source_url = f"https://example.com/concurrent-{uuid4()}"

    def write() -> str:
        repository = PostgresKnowledgePersistenceRepository()
        document = KnowledgeDocumentRecord(
            id=str(uuid4()),
            source_url=source_url,
            title="Concurrent guide",
            content_hash="concurrent-v1",
            access_roles=("user",),
        )
        item = PersistedKnowledgeChunk(
            id=str(uuid5(NAMESPACE_URL, f"{source_url}\0chunk")),
            document_id=document.id,
            sequence=0,
            text="Concurrent persistence knowledge",
            content_hash="concurrent-chunk-v1",
            embedding=tuple([1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1)),
            heading_path=(),
            access_roles=("user",),
        )
        return repository.replace_document(document, [item]).action

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            actions = list(executor.map(lambda _: write(), range(2)))

        with get_connection() as connection:
            counts = connection.execute(
                """
                SELECT count(DISTINCT documents.id), count(chunks.id)
                FROM documents JOIN chunks ON chunks.doc_id = documents.id
                WHERE documents.source_url = %s
                """,
                (source_url,),
            ).fetchone()

        assert sorted(actions) == ["created", "unchanged"]
        assert counts == (1, 1)
    finally:
        delete_document(source_url)
