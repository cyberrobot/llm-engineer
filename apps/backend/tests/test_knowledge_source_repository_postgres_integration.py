import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from uuid import UUID, uuid4

import psycopg
import pytest

from assistant.application.knowledge_persistence_service import KnowledgePersistenceService
from assistant.application.knowledge_source_service import (
    ActiveIngestionConflict,
    IdempotencyConflict,
    KnowledgeSourceNotFound,
    KnowledgeSourceService,
)
from assistant.application.retrieval_service import RetrievalService
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, DocumentRetrievalState
from assistant.domain.content_processing_result import ContentProcessingResult
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_chunk import KnowledgeChunk
from assistant.domain.knowledge_persistence import PersistenceMode
from assistant.domain.knowledge_source import KnowledgeSource, KnowledgeSourceType
from assistant.infrastructure.repositories import VectorKnowledgeRepository
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from assistant.infrastructure.repositories.knowledge_persistence import (
    PostgresKnowledgePersistenceRepository,
)
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from assistant.infrastructure.vector_store.pgvector import PgVectorStore
from core.config import DATABASE_URL, EMBEDDING_VECTOR_DIMENSIONS
from infrastructure.database.connection import get_connection, init_db


def _require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for knowledge-source PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def _service() -> KnowledgeSourceService:
    return KnowledgeSourceService(
        PostgresKnowledgeSourceRepository(), PostgresAssistantRepository()
    )


def _complete(job_id: UUID) -> None:
    with get_connection() as connection:
        connection.execute(
            """UPDATE document_ingestion_jobs
               SET status='completed', started_at=NOW(), completed_at=NOW(), updated_at=NOW()
               WHERE id=%s""",
            (str(job_id),),
        )


class _EmbeddingProvider:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.query_calls = 0

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        self.batch_calls += 1
        return [[1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1) for _ in texts]

    def generate_embedding(self, *, text: str) -> list[float]:
        self.query_calls += 1
        return [1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1)


def _processed(source_url: str, version: str, text: str) -> ContentProcessingResult:
    chunk = KnowledgeChunk(
        id=uuid4(),
        source_url=source_url,
        title="Authority",
        sequence=0,
        text=text,
        content_hash=f"{version}-chunk",
        document_content_hash=version,
        heading_path=(),
        character_count=len(text),
    )
    return ContentProcessingResult(1, 1, 0, 1, [chunk], [], 1)


def _cleanup(document_ids: set[str], assistant_ids: set[UUID] | None = None) -> None:
    if not document_ids and not assistant_ids:
        return
    ids = list(document_ids)
    with get_connection() as connection:
        if ids:
            connection.execute(
                "DELETE FROM ingestion_persistence_results WHERE document_id = ANY(%s)", (ids,)
            )
            connection.execute(
                """DELETE FROM ingestion_step_executions WHERE ingestion_job_id IN
                   (SELECT id FROM document_ingestion_jobs WHERE document_id = ANY(%s))""",
                (ids,),
            )
            connection.execute(
                "UPDATE documents SET last_ingestion_job_id=NULL WHERE id = ANY(%s)", (ids,)
            )
            connection.execute("DELETE FROM chunks WHERE doc_id = ANY(%s)", (ids,))
            connection.execute(
                """DELETE FROM knowledge_source_reingestion_requests WHERE source_id IN
                   (SELECT id FROM knowledge_sources WHERE document_id = ANY(%s))""",
                (ids,),
            )
            connection.execute(
                "DELETE FROM document_ingestion_jobs WHERE document_id = ANY(%s)", (ids,)
            )
            connection.execute("DELETE FROM knowledge_sources WHERE document_id = ANY(%s)", (ids,))
            connection.execute("DELETE FROM documents WHERE id = ANY(%s)", (ids,))
            remaining = connection.execute(
                """SELECT
                     (SELECT count(*) FROM knowledge_sources WHERE document_id = ANY(%s)),
                     (SELECT count(*) FROM documents WHERE id = ANY(%s))""",
                (ids, ids),
            ).fetchone()
            assert remaining == (0, 0)
        if assistant_ids:
            connection.execute(
                "DELETE FROM assistants WHERE id = ANY(%s)",
                ([str(value) for value in assistant_ids],),
            )


def test_repository_creation_isolation_reingestion_deletion_and_rollback():
    _require_database()
    init_db()
    service = _service()
    other_assistant = uuid4()
    documents: set[str] = set()
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO assistants (id, slug, name, status, visibility)
               VALUES (%s, %s, 'Other', 'active', 'private')""",
            (str(other_assistant), f"other-{other_assistant.hex}"),
        )

    try:
        direct, direct_reused = service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.direct_text,
            name="Operations",
            direct_text="Safe fictional operational guidance.",
            idempotency_key=f"direct-{uuid4()}",
        )
        documents.add(direct.source.document_id)
        assert direct_reused is False
        assert direct.source.direct_text == "Safe fictional operational guidance."

        url_key = f"url-{uuid4()}"
        url, url_reused = service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.url,
            name="Website",
            url="HTTPS://EXAMPLE.COM:443/guide",
            idempotency_key=url_key,
        )
        documents.add(url.source.document_id)
        assert url_reused is False
        assert url.source.url == "https://example.com/guide"

        replay, replayed = service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.url,
            name="Website",
            url="https://example.com/guide",
            idempotency_key=url_key,
        )
        assert replayed is True
        assert replay.source.id == url.source.id
        with pytest.raises(IdempotencyConflict):
            service.create(
                REDMOOR_ASSISTANT_ID,
                source_type=KnowledgeSourceType.url,
                name="Conflict",
                url="https://example.com/different",
                idempotency_key=url_key,
            )

        isolated, isolated_reused = service.create(
            other_assistant,
            source_type=KnowledgeSourceType.url,
            name="Website",
            url="https://example.com/guide",
            idempotency_key=url_key,
        )
        documents.add(isolated.source.document_id)
        assert isolated_reused is False
        assert isolated.source.id != url.source.id
        assert service.repository.find_by_url(other_assistant, url.source.url) == isolated.source
        with pytest.raises(KnowledgeSourceNotFound):
            service.get(other_assistant, url.source.id)

        active, active_reused = service.reingest(
            REDMOOR_ASSISTANT_ID, url.source.id, idempotency_key=f"active-{uuid4()}"
        )
        assert active_reused is True
        assert active.latest_job.id == url.latest_job.id
        with pytest.raises(ActiveIngestionConflict):
            service.delete(REDMOOR_ASSISTANT_ID, url.source.id)

        _complete(url.latest_job.id)
        terminal, terminal_reused = service.reingest(
            REDMOOR_ASSISTANT_ID, url.source.id, idempotency_key=f"terminal-{uuid4()}"
        )
        assert terminal_reused is False
        assert terminal.latest_job.id != url.latest_job.id
        _complete(terminal.latest_job.id)

        service.delete(REDMOOR_ASSISTANT_ID, url.source.id)
        documents.remove(url.source.document_id)
        assert service.repository.get(REDMOOR_ASSISTANT_ID, url.source.id) is None

        rolled_back = KnowledgeSource.create(
            assistant_id=REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.direct_text,
            name="Rollback",
            direct_text="This transaction must not persist.",
        )
        job = DocumentIngestionJob.create(rolled_back.document_id)
        with pytest.raises(RuntimeError, match="forced failure"):
            with service.repository.transaction() as transaction:
                transaction.create(rolled_back, job, "c" * 64, None)
                raise RuntimeError("forced failure")
        with get_connection() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM documents WHERE id=%s", (rolled_back.document_id,)
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM knowledge_sources WHERE id=%s", (str(rolled_back.id),)
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM document_ingestion_jobs WHERE id=%s", (str(job.id),)
                ).fetchone()[0]
                == 0
            )
    finally:
        _cleanup(documents, {other_assistant})


def test_concurrent_url_creation_and_reingestion_have_one_canonical_outcome():
    _require_database()
    init_db()
    service = _service()
    unique_path = uuid4().hex
    documents: set[str] = set()
    create_barrier = Barrier(2)

    def create_url():
        first_call = True

        @contextmanager
        def create_connection():
            nonlocal first_call
            if first_call:
                first_call = False
                create_barrier.wait(timeout=5)
            with get_connection() as connection:
                yield connection

        return KnowledgeSourceService(
            PostgresKnowledgeSourceRepository(create_connection),
            PostgresAssistantRepository(),
        ).create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.url,
            name="Concurrent",
            url=f"https://example.com/{unique_path}",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            creations = list(executor.map(lambda _: create_url(), range(2)))
        source_ids = {result[0].source.id for result in creations}
        document_ids = {result[0].source.document_id for result in creations}
        job_ids = {result[0].latest_job.id for result in creations}
        documents.update(document_ids)
        assert len(source_ids) == len(document_ids) == len(job_ids) == 1
        assert sorted(result[1] for result in creations) == [False, True]
        with get_connection() as connection:
            canonical_counts = connection.execute(
                """SELECT
                     (SELECT count(*) FROM knowledge_sources WHERE id=%s),
                     (SELECT count(*) FROM documents WHERE id=%s),
                     (SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s)""",
                (
                    str(next(iter(source_ids))),
                    next(iter(document_ids)),
                    next(iter(document_ids)),
                ),
            ).fetchone()
        assert canonical_counts == (1, 1, 1)

        initial_job = creations[0][0].latest_job
        _complete(initial_job.id)
        source_id = creations[0][0].source.id
        key = f"concurrent-reingestion-{uuid4()}"
        reingest_barrier = Barrier(2)

        def reingest():
            first_call = True

            @contextmanager
            def reingest_connection():
                nonlocal first_call
                if first_call:
                    first_call = False
                    reingest_barrier.wait(timeout=5)
                with get_connection() as connection:
                    yield connection

            return KnowledgeSourceService(
                PostgresKnowledgeSourceRepository(reingest_connection),
                PostgresAssistantRepository(),
            ).reingest(REDMOOR_ASSISTANT_ID, source_id, idempotency_key=key)

        with ThreadPoolExecutor(max_workers=2) as executor:
            reingestions = list(executor.map(lambda _: reingest(), range(2)))
        assert len({result[0].latest_job.id for result in reingestions}) == 1
        assert sorted(result[1] for result in reingestions) == [False, True]
        replayed, replay_reused = service.reingest(
            REDMOOR_ASSISTANT_ID, source_id, idempotency_key=key
        )
        assert replayed.latest_job.id == reingestions[0][0].latest_job.id
        assert replay_reused is True
        other, _ = service.create(
            REDMOOR_ASSISTANT_ID,
            source_type=KnowledgeSourceType.direct_text,
            name="Conflicting receipt owner",
            direct_text="A different source cannot reuse this receipt key.",
        )
        documents.add(other.source.document_id)
        with pytest.raises(IdempotencyConflict):
            service.reingest(
                REDMOOR_ASSISTANT_ID,
                other.source.id,
                idempotency_key=key,
            )
        with get_connection() as connection:
            assert (
                connection.execute(
                    """SELECT count(*) FROM document_ingestion_jobs
                   WHERE document_id=%s AND status IN ('queued', 'running')""",
                    (next(iter(document_ids)),),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    """SELECT count(*) FROM knowledge_source_reingestion_requests
                   WHERE assistant_id=%s AND idempotency_key=%s""",
                    (str(REDMOOR_ASSISTANT_ID), key),
                ).fetchone()[0]
                == 1
            )
    finally:
        _cleanup(documents)


def test_reingestion_rolls_back_job_and_receipt_when_receipt_insert_fails():
    _require_database()
    init_db()
    service = _service()
    created, _ = service.create(
        REDMOOR_ASSISTANT_ID,
        source_type=KnowledgeSourceType.direct_text,
        name="Re-ingestion rollback",
        direct_text="Rollback-safe fictional guidance.",
    )
    document_id = created.source.document_id
    _complete(created.latest_job.id)
    new_job = DocumentIngestionJob.create(document_id)
    key = f"rollback-{uuid4()}"

    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            with service.repository.transaction() as transaction:
                transaction.reingest(
                    REDMOOR_ASSISTANT_ID,
                    created.source.id,
                    new_job,
                    "not-a-sha256-hash",
                    key,
                )

        with get_connection() as connection:
            jobs = connection.execute(
                "SELECT id, status FROM document_ingestion_jobs WHERE document_id=%s ORDER BY created_at",
                (document_id,),
            ).fetchall()
            receipts = connection.execute(
                "SELECT count(*) FROM knowledge_source_reingestion_requests WHERE source_id=%s",
                (str(created.source.id),),
            ).fetchone()[0]
            stored_source = connection.execute(
                "SELECT name, retrieval_state FROM knowledge_sources WHERE id=%s",
                (str(created.source.id),),
            ).fetchone()
        assert jobs == [(str(created.latest_job.id), "completed")]
        assert receipts == 0
        assert stored_source == ("Re-ingestion rollback", "enabled")

        legitimate, reused = service.reingest(
            REDMOOR_ASSISTANT_ID, created.source.id, idempotency_key=key
        )
        assert reused is False
        assert legitimate.latest_job.id != created.latest_job.id
    finally:
        _cleanup({document_id})


def test_delete_rolls_back_document_source_chunks_history_and_receipts():
    _require_database()
    init_db()
    service = _service()
    created, _ = service.create(
        REDMOOR_ASSISTANT_ID,
        source_type=KnowledgeSourceType.direct_text,
        name="Deletion rollback",
        direct_text="Atomic deletion fictional guidance.",
    )
    document_id = created.source.document_id
    _complete(created.latest_job.id)
    receipt_key = f"delete-rollback-{uuid4()}"
    reingested, _ = service.reingest(
        REDMOOR_ASSISTANT_ID, created.source.id, idempotency_key=receipt_key
    )
    _complete(reingested.latest_job.id)

    try:
        with get_connection() as connection:
            connection.execute(
                """INSERT INTO chunks
                   (id, doc_id, text, embedding, access_roles, sequence, content_hash, assistant_id)
                   VALUES (%s, %s, 'Rollback chunk', %s, '["user"]'::jsonb, 0, %s, %s)""",
                (
                    str(uuid4()),
                    document_id,
                    [1.0] + [0.0] * (EMBEDDING_VECTOR_DIMENSIONS - 1),
                    "d" * 64,
                    str(REDMOOR_ASSISTANT_ID),
                ),
            )

        with pytest.raises(RuntimeError, match="abort deletion"):
            with get_connection() as connection:
                transactional_repository = PostgresKnowledgeSourceRepository(lambda: connection)
                with transactional_repository.transaction() as transaction:
                    assert transaction.delete(REDMOOR_ASSISTANT_ID, created.source.id) is True
                    raise RuntimeError("abort deletion")

        with get_connection() as connection:
            counts = connection.execute(
                """SELECT
                     (SELECT count(*) FROM knowledge_sources WHERE id=%s),
                     (SELECT count(*) FROM documents WHERE id=%s),
                     (SELECT count(*) FROM chunks WHERE doc_id=%s),
                     (SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s),
                     (SELECT count(*) FROM knowledge_source_reingestion_requests WHERE source_id=%s),
                     (SELECT retrieval_state FROM documents WHERE id=%s)""",
                (
                    str(created.source.id),
                    document_id,
                    document_id,
                    document_id,
                    str(created.source.id),
                    document_id,
                ),
            ).fetchone()
        assert counts == (1, 1, 1, 2, 1, "enabled")
    finally:
        _cleanup({document_id})


def test_retrieval_state_remains_authoritative_across_ingestion_completion():
    _require_database()
    init_db()
    service = _service()
    view, _ = service.create(
        REDMOOR_ASSISTANT_ID,
        source_type=KnowledgeSourceType.direct_text,
        name="Authority",
        direct_text="Retrieval state remains administrator controlled.",
    )
    document_id = view.source.document_id
    provider = _EmbeddingProvider()
    persistence = KnowledgePersistenceService(
        provider,
        PostgresKnowledgePersistenceRepository(),
        assistant_id=REDMOOR_ASSISTANT_ID,
        embedding_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
        embedding_batch_size=100,
    )
    retrieval = RetrievalService(
        provider,
        VectorKnowledgeRepository(PgVectorStore()),
        assistant_id=REDMOOR_ASSISTANT_ID,
        limit=20,
        min_score=0.99,
    )
    source_url = f"urn:redmoor:knowledge-source:{view.source.id}"
    try:
        initial = persistence.prepare(
            _processed(source_url, "1" * 64, "Initial authoritative knowledge"),
            force_replace=True,
        )
        persistence.persist_prepared(
            initial,
            command=persistence.create_command(
                initial,
                ingestion_job_id=view.latest_job.id,
                document_id=document_id,
                mode=PersistenceMode.reindex,
            ),
        )
        assert any(item.document.id == document_id for item in retrieval.retrieve("authority"))
        _complete(view.latest_job.id)
        reingested, reused = service.reingest(REDMOOR_ASSISTANT_ID, view.source.id)
        assert reused is False
        replacement = persistence.prepare(
            _processed(source_url, "2" * 64, "Replacement authoritative knowledge"),
            force_replace=True,
        )

        disabled = service.update(
            REDMOOR_ASSISTANT_ID, view.source.id, DocumentRetrievalState.disabled
        )
        persistence.persist_prepared(
            replacement,
            command=persistence.create_command(
                replacement,
                ingestion_job_id=reingested.latest_job.id,
                document_id=document_id,
                mode=PersistenceMode.reindex,
            ),
        )
        assert disabled.source.retrieval_state is DocumentRetrievalState.disabled
        with get_connection() as connection:
            states = connection.execute(
                """SELECT knowledge_sources.retrieval_state, documents.retrieval_state
                   FROM knowledge_sources JOIN documents
                     ON documents.id=knowledge_sources.document_id
                   WHERE knowledge_sources.id=%s""",
                (str(view.source.id),),
            ).fetchone()
            job_count = connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s",
                (document_id,),
            ).fetchone()[0]
            chunks_before_enable = connection.execute(
                "SELECT id, text, embedding::text FROM chunks WHERE doc_id=%s ORDER BY sequence",
                (document_id,),
            ).fetchall()
        assert states == ("disabled", "disabled")
        assert not any(item.document.id == document_id for item in retrieval.retrieve("authority"))

        embedding_calls = provider.batch_calls
        enabled = service.update(
            REDMOOR_ASSISTANT_ID, view.source.id, DocumentRetrievalState.enabled
        )
        assert enabled.source.retrieval_state is DocumentRetrievalState.enabled
        matching = [
            item for item in retrieval.retrieve("authority") if item.document.id == document_id
        ]
        assert [item.content for item in matching] == ["Replacement authoritative knowledge"]
        with get_connection() as connection:
            assert (
                connection.execute(
                    "SELECT retrieval_state FROM documents WHERE id=%s", (document_id,)
                ).fetchone()[0]
                == "enabled"
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s",
                    (document_id,),
                ).fetchone()[0]
                == job_count
            )
            assert (
                connection.execute(
                    "SELECT id, text, embedding::text FROM chunks WHERE doc_id=%s ORDER BY sequence",
                    (document_id,),
                ).fetchall()
                == chunks_before_enable
            )
        assert provider.batch_calls == embedding_calls
    finally:
        _cleanup({document_id})
