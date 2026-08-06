import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import psycopg
import pytest
from psycopg import sql

from assistant.application.knowledge_persistence_service import (
    IngestionPersistenceConflictError,
    KnowledgePersistenceError,
    KnowledgePersistenceService,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.knowledge_persistence import (
    KnowledgeDocumentRecord,
    PersistedKnowledgeChunk,
    PersistenceMode,
)
from assistant.infrastructure.repositories.document_ingestion_job import (
    PostgresDocumentIngestionJobRepository,
)
from assistant.infrastructure.repositories.knowledge_persistence import (
    PostgresKnowledgePersistenceRepository,
)
from assistant.infrastructure.storage import search_chunks_by_embedding
from assistant.infrastructure.vector_store.pgvector import PgVectorStore
from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.transactional_ingestion_persistence import (
    downgrade as downgrade_transactional_persistence,
)
from infrastructure.database.migrations.transactional_ingestion_persistence import (
    upgrade as upgrade_transactional_persistence,
)


class DeterministicEmbeddingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1) for _ in texts]


def require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for knowledge-persistence PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


class FailAfterStatementCursor:
    def __init__(self, cursor: Any, statement_fragment: str) -> None:
        self._cursor = cursor
        self._statement_fragment = " ".join(statement_fragment.split())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def execute(self, query: Any, parameters: Any = None) -> Any:
        result = self._cursor.execute(query, parameters)
        normalised_query = " ".join(str(query).split())
        if self._statement_fragment in normalised_query:
            raise RuntimeError(f"injected failure after {self._statement_fragment}")
        return result


class FailAfterStatementConnection:
    def __init__(self, connection: Any, statement_fragment: str) -> None:
        self._connection = connection
        self._statement_fragment = statement_fragment

    @contextmanager
    def cursor(self):
        with self._connection.cursor() as cursor:
            yield FailAfterStatementCursor(cursor, self._statement_fragment)


def failing_connection_factory(statement_fragment: str):
    @contextmanager
    def factory():
        with get_connection() as connection:
            yield FailAfterStatementConnection(connection, statement_fragment)

    return factory


def persistence_service(
    repository: PostgresKnowledgePersistenceRepository | None = None,
) -> tuple[KnowledgePersistenceService, DeterministicEmbeddingProvider]:
    provider = DeterministicEmbeddingProvider()
    return (
        KnowledgePersistenceService(
            provider,
            repository or PostgresKnowledgePersistenceRepository(),
            assistant_id=REDMOOR_ASSISTANT_ID,
            embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
            embedding_batch_size=100,
        ),
        provider,
    )


def stored_representation(source_url: str) -> tuple[Any, list[Any]]:
    with get_connection() as connection:
        document = connection.execute(
            """
            SELECT id, title, content_hash, access_roles, last_ingestion_job_id
            FROM documents WHERE source_url = %s AND assistant_id = %s
            """,
            (source_url, str(REDMOOR_ASSISTANT_ID)),
        ).fetchone()
        chunks = connection.execute(
            """
            SELECT chunks.text, chunks.content_hash, chunks.access_roles,
                   chunks.embedding::text, chunks.ingestion_job_id
            FROM chunks JOIN documents ON documents.id = chunks.doc_id
            WHERE documents.source_url = %s AND documents.assistant_id = %s
            ORDER BY chunks.sequence
            """,
            (source_url, str(REDMOOR_ASSISTANT_ID)),
        ).fetchall()
    return document, chunks


def role_filtered_texts(source_url: str, role: str) -> list[str]:
    with get_connection() as connection:
        document_id = connection.execute(
            "SELECT id FROM documents WHERE source_url = %s AND assistant_id = %s",
            (source_url, str(REDMOOR_ASSISTANT_ID)),
        ).fetchone()[0]
    matches = search_chunks_by_embedding(
        REDMOOR_ASSISTANT_ID,
        [1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1),
        "persistence knowledge",
        role,
        limit=50,
    )
    return [str(item["text"]) for item in matches if item["doc_id"] == document_id]


def processed(
    source_url: str,
    *,
    version: str,
    texts: list[str],
    title: str = "Persistence integration guide",
) -> ContentProcessingResult:
    chunks = [
        KnowledgeChunk(
            id=uuid5(NAMESPACE_URL, f"{source_url}\0{version}\0{index}"),
            source_url=source_url,
            title=title,
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


def test_required_database_mode_fails_instead_of_skipping(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED", "true")
    monkeypatch.setattr(sys.modules[__name__], "DATABASE_URL", "postgresql://unavailable")

    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError("injected unavailable database")

    monkeypatch.setattr(psycopg, "connect", unavailable)

    with pytest.raises(
        pytest.fail.Exception, match="Required PostgreSQL test database is unavailable"
    ):
        require_database()


def test_document_creation_failure_rolls_back_all_knowledge():
    require_database()
    init_db()
    source_url = f"https://example.com/create-failure-{uuid4()}"
    repository = PostgresKnowledgePersistenceRepository(
        failing_connection_factory("INSERT INTO documents (")
    )
    service, _ = persistence_service(repository)

    try:
        with pytest.raises(KnowledgePersistenceError, match="could not be persisted"):
            service.persist(processed(source_url, version="v1", texts=["Uncommitted knowledge"]))

        assert stored_representation(source_url) == (None, [])
    finally:
        delete_document(source_url)


def test_obsolete_chunk_deletion_failure_preserves_previous_retrievable_representation():
    require_database()
    init_db()
    source_url = f"https://example.com/delete-failure-{uuid4()}"
    healthy_service, _ = persistence_service()

    try:
        healthy_service.persist(
            processed(source_url, version="v1", texts=["Old persistence knowledge"]),
            access_roles=("user",),
        )
        before = stored_representation(source_url)
        failing_service, _ = persistence_service(
            PostgresKnowledgePersistenceRepository(
                failing_connection_factory("DELETE FROM chunks WHERE doc_id = %s")
            )
        )

        with pytest.raises(KnowledgePersistenceError, match="could not be persisted"):
            failing_service.persist(
                processed(source_url, version="v2", texts=["Proposed replacement knowledge"]),
                access_roles=("user",),
            )

        assert stored_representation(source_url) == before
        assert role_filtered_texts(source_url, "user") == ["Old persistence knowledge"]
        assert role_filtered_texts(source_url, "manager") == []
    finally:
        delete_document(source_url)


def test_metadata_update_failure_preserves_document_chunk_roles_and_authorization():
    require_database()
    init_db()
    source_url = f"https://example.com/metadata-failure-{uuid4()}"
    healthy_service, _ = persistence_service()

    try:
        healthy_service.persist(
            processed(
                source_url,
                version="v1",
                texts=["Metadata persistence knowledge"],
                title="Original title",
            ),
            access_roles=("user",),
        )
        before = stored_representation(source_url)
        failing_service, provider = persistence_service(
            PostgresKnowledgePersistenceRepository(
                failing_connection_factory("UPDATE documents SET title = %s")
            )
        )

        with pytest.raises(KnowledgePersistenceError, match="could not be persisted"):
            failing_service.persist(
                processed(
                    source_url,
                    version="v1",
                    texts=["Metadata persistence knowledge"],
                    title="Proposed title",
                ),
                access_roles=("manager",),
            )

        assert provider.calls == 0
        assert stored_representation(source_url) == before
        assert role_filtered_texts(source_url, "user") == ["Metadata persistence knowledge"]
        assert role_filtered_texts(source_url, "manager") == []
    finally:
        delete_document(source_url)


def test_processed_knowledge_is_idempotent_retrievable_and_replaces_stale_chunks():
    require_database()
    init_db()
    source_url = f"https://example.com/integration-{uuid4()}"
    repository = PostgresKnowledgePersistenceRepository()
    provider = DeterministicEmbeddingProvider()
    service = KnowledgePersistenceService(
        provider,
        repository,
        assistant_id=REDMOOR_ASSISTANT_ID,
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
            assistant_id=REDMOOR_ASSISTANT_ID,
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
        assistant_id=REDMOOR_ASSISTANT_ID,
        source_url=source_url,
        title="Rollback guide",
        content_hash="rollback-v1",
        access_roles=("user",),
    )
    duplicate_id = str(uuid4())
    chunks = [
        PersistedKnowledgeChunk(
            id=duplicate_id,
            assistant_id=REDMOOR_ASSISTANT_ID,
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
        service, _ = persistence_service()
        result = service.persist(
            processed(
                source_url,
                version="concurrent-v1",
                texts=["Concurrent persistence knowledge"],
                title="Concurrent guide",
            )
        )
        return "created" if result.documents_created else "unchanged"

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
        assert role_filtered_texts(source_url, "user") == ["Concurrent persistence knowledge"]
    finally:
        delete_document(source_url)


class FailBeforeCommitRepository(PostgresKnowledgePersistenceRepository):
    @contextmanager
    def transaction(self):
        with super().transaction() as transaction:

            class FailBeforeCommit:
                def __getattr__(self, name):
                    return getattr(transaction, name)

                def record_committed_result(self, command, result):
                    transaction.record_committed_result(command, result)
                    raise RuntimeError("injected failure after representation activation")

            yield FailBeforeCommit()


def test_pipeline_persistence_rolls_back_reindex_and_replays_one_committed_result():
    require_database()
    init_db()
    source_url = f"https://example.com/transaction-{uuid4()}"
    document_id = str(uuid4())
    provider = DeterministicEmbeddingProvider()

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, doc_type, access_roles, status, source_url, title, content_hash, assistant_id
                ) VALUES (%s, 'website', '[\"user\"]'::jsonb, 'indexed', %s, 'Old', 'v1', %s)
                """,
                (document_id, source_url, str(REDMOOR_ASSISTANT_ID)),
            )
            connection.execute(
                """
                INSERT INTO chunks (
                    id, doc_id, text, embedding, access_roles, sequence, content_hash, assistant_id
                ) VALUES (
                    %s, %s, 'Old active knowledge', %s, '[\"user\"]'::jsonb, 0, 'v1-chunk-0', %s
                )
                """,
                (
                    str(uuid4()),
                    document_id,
                    [1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1),
                    str(REDMOOR_ASSISTANT_ID),
                ),
            )
        job = PostgresDocumentIngestionJobRepository().create(
            DocumentIngestionJob.create(document_id)
        )
        failing_service = KnowledgePersistenceService(
            provider,
            FailBeforeCommitRepository(),
            assistant_id=REDMOOR_ASSISTANT_ID,
            embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
            embedding_batch_size=100,
        )
        prepared = failing_service.prepare(
            processed(source_url, version="v2", texts=["New replacement knowledge"])
        )
        command = failing_service.create_command(
            prepared,
            ingestion_job_id=job.id,
            document_id=document_id,
            mode=PersistenceMode.reindex,
        )
        competing_job = PostgresDocumentIngestionJobRepository().create(
            DocumentIngestionJob.create(document_id)
        )
        competing_prepared = failing_service.prepare(
            processed(source_url, version="v3", texts=["Stale competing knowledge"]),
            force_replace=True,
        )
        competing_command = failing_service.create_command(
            competing_prepared,
            ingestion_job_id=competing_job.id,
            document_id=document_id,
            mode=PersistenceMode.reindex,
        )

        with pytest.raises(Exception, match="could not be persisted"):
            failing_service.persist_prepared(prepared, command=command)

        with get_connection() as connection:
            rolled_back = connection.execute(
                """
                SELECT documents.content_hash, chunks.text,
                       (SELECT count(*) FROM ingestion_persistence_results
                        WHERE ingestion_job_id = %s)
                FROM documents JOIN chunks ON chunks.doc_id = documents.id
                WHERE documents.id = %s
                """,
                (str(job.id), document_id),
            ).fetchone()
        assert rolled_back == ("v1", "Old active knowledge", 0)

        healthy_service = KnowledgePersistenceService(
            provider,
            PostgresKnowledgePersistenceRepository(),
            assistant_id=REDMOOR_ASSISTANT_ID,
            embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
            embedding_batch_size=100,
        )
        committed = healthy_service.persist_prepared(prepared, command=command)
        reconstructed = healthy_service.prepare(
            processed(source_url, version="v2", texts=["New replacement knowledge"]),
            force_replace=True,
        )
        replay_command = healthy_service.create_command(
            reconstructed,
            ingestion_job_id=job.id,
            document_id=document_id,
            mode=PersistenceMode.reindex,
        )
        assert replay_command.command_hash == command.command_hash
        replayed = healthy_service.persist_prepared(reconstructed, command=replay_command)
        with pytest.raises(IngestionPersistenceConflictError):
            healthy_service.persist_prepared(competing_prepared, command=competing_command)

        with get_connection() as connection:
            final = connection.execute(
                """
                SELECT documents.content_hash, documents.last_ingestion_job_id,
                       count(chunks.id), min(chunks.text),
                       count(DISTINCT chunks.ingestion_job_id),
                       (SELECT count(*) FROM ingestion_persistence_results
                        WHERE ingestion_job_id IN (%s, %s))
                FROM documents JOIN chunks ON chunks.doc_id = documents.id
                WHERE documents.id = %s
                GROUP BY documents.content_hash, documents.last_ingestion_job_id
                """,
                (str(job.id), str(competing_job.id), document_id),
            ).fetchone()

        assert replayed == committed
        assert final == ("v2", str(job.id), 1, "New replacement knowledge", 1, 1)
    finally:
        if "job" in locals():
            with suppress(Exception), get_connection() as connection:
                connection.execute(
                    "DELETE FROM ingestion_persistence_results WHERE ingestion_job_id = %s",
                    (str(job.id),),
                )
                connection.execute(
                    "DELETE FROM document_ingestion_jobs WHERE id = %s", (str(job.id),)
                )
                if "competing_job" in locals():
                    connection.execute(
                        "DELETE FROM document_ingestion_jobs WHERE id = %s",
                        (str(competing_job.id),),
                    )
                connection.execute("DELETE FROM documents WHERE source_url = %s", (source_url,))
        else:
            delete_document(source_url)


def test_transactional_persistence_migration_preserves_existing_index_and_is_reversible():
    require_database()
    schema = f"transactional_persistence_{uuid4().hex}"
    connection = psycopg.connect(DATABASE_URL)
    try:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        connection.execute(
            "CREATE TABLE documents (id TEXT PRIMARY KEY, source_url TEXT, content_hash TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE document_ingestion_jobs (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL REFERENCES documents(id),
                text TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO documents VALUES ('legacy-document', 'https://example.com/legacy', 'v1')"
        )
        connection.execute(
            "INSERT INTO chunks VALUES ('legacy-chunk', 'legacy-document', 'Legacy knowledge')"
        )

        upgrade_transactional_persistence(connection.cursor())
        upgrade_transactional_persistence(connection.cursor())
        legacy = connection.execute(
            """
            SELECT documents.last_ingestion_job_id, chunks.ingestion_job_id, chunks.text
            FROM documents JOIN chunks ON chunks.doc_id = documents.id
            WHERE documents.id = 'legacy-document'
            """
        ).fetchone()
        assert legacy == (None, None, "Legacy knowledge")

        downgrade_transactional_persistence(connection.cursor())
        downgraded_columns = {
            row[0]
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = %s AND table_name IN ('documents', 'chunks')
                """,
                (schema,),
            ).fetchall()
        }
        assert "last_ingestion_job_id" not in downgraded_columns
        assert "ingestion_job_id" not in downgraded_columns
        assert connection.execute(
            "SELECT text FROM chunks WHERE id = 'legacy-chunk'"
        ).fetchone() == ("Legacy knowledge",)

        upgrade_transactional_persistence(connection.cursor())
        assert (
            connection.execute("SELECT to_regclass('ingestion_persistence_results')").fetchone()[0]
            is not None
        )
        connection.commit()
    finally:
        connection.rollback()
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )
        connection.commit()
        connection.close()


def test_live_persistence_schema_matches_retrieval_and_idempotency_contracts():
    require_database()
    init_db()

    with get_connection() as connection:
        extension = connection.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        vector_type = connection.execute(
            """
            SELECT format_type(attribute.atttypid, attribute.atttypmod)
            FROM pg_attribute AS attribute
            JOIN pg_class AS relation ON relation.oid = attribute.attrelid
            WHERE relation.relname = 'chunks' AND attribute.attname = 'embedding'
              AND attribute.attnum > 0 AND NOT attribute.attisdropped
            """
        ).fetchone()
        indexes = {
            row[0]
            for row in connection.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname IN (
                    'documents_assistant_source_url_unique_idx',
                    'chunks_document_sequence_unique_idx',
                    'chunks_document_content_hash_unique_idx'
                  )
                """
            ).fetchall()
        }
        cascading_chunk_foreign_keys = connection.execute(
            """
            SELECT count(*)
            FROM pg_constraint AS constraint_record
            JOIN pg_class AS relation ON relation.oid = constraint_record.conrelid
            WHERE relation.relname = 'chunks'
              AND constraint_record.contype = 'f'
              AND constraint_record.confdeltype = 'c'
            """
        ).fetchone()[0]

    assert extension == ("vector",)
    assert vector_type == (f"vector({EMBEDDING_VECTOR_DIMENSIONS})",)
    assert indexes == {
        "documents_assistant_source_url_unique_idx",
        "chunks_document_sequence_unique_idx",
        "chunks_document_content_hash_unique_idx",
    }
    assert cascading_chunk_foreign_keys >= 1
