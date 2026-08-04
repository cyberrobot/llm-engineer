from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from uuid import UUID, uuid4

import psycopg
import pytest

from assistant.application.knowledge_source_service import (
    ActiveIngestionConflict,
    IdempotencyConflict,
    KnowledgeSourceNotFound,
    KnowledgeSourceService,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource, KnowledgeSourceType
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db


def _require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
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


def _cleanup(document_ids: set[str], assistant_ids: set[UUID] | None = None) -> None:
    with suppress(Exception), get_connection() as connection:
        connection.execute(
            "DELETE FROM documents WHERE id = ANY(%s)", (list(document_ids),)
        )
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
            assert connection.execute(
                "SELECT count(*) FROM documents WHERE id=%s", (rolled_back.document_id,)
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT count(*) FROM knowledge_sources WHERE id=%s", (str(rolled_back.id),)
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE id=%s", (str(job.id),)
            ).fetchone()[0] == 0
    finally:
        _cleanup(documents, {other_assistant})


def test_concurrent_url_creation_and_reingestion_have_one_canonical_outcome():
    _require_database()
    init_db()
    unique_path = uuid4().hex
    documents: set[str] = set()

    def create_url():
        return _service().create(
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

        initial_job = creations[0][0].latest_job
        _complete(initial_job.id)
        source_id = creations[0][0].source.id
        key = f"concurrent-reingestion-{uuid4()}"

        def reingest():
            return _service().reingest(
                REDMOOR_ASSISTANT_ID, source_id, idempotency_key=key
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            reingestions = list(executor.map(lambda _: reingest(), range(2)))
        assert len({result[0].latest_job.id for result in reingestions}) == 1
        assert sorted(result[1] for result in reingestions) == [False, True]
        with get_connection() as connection:
            assert connection.execute(
                """SELECT count(*) FROM document_ingestion_jobs
                   WHERE document_id=%s AND status IN ('queued', 'running')""",
                (next(iter(document_ids)),),
            ).fetchone()[0] == 1
    finally:
        _cleanup(documents)


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
    try:
        disabled = service.update(
            REDMOOR_ASSISTANT_ID, view.source.id, DocumentRetrievalState.disabled
        )
        assert disabled.source.retrieval_state is DocumentRetrievalState.disabled
        _complete(view.latest_job.id)
        with get_connection() as connection:
            state = connection.execute(
                "SELECT retrieval_state FROM documents WHERE id=%s", (document_id,)
            ).fetchone()[0]
            job_count = connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s",
                (document_id,),
            ).fetchone()[0]
        assert state == "disabled"

        enabled = service.update(
            REDMOOR_ASSISTANT_ID, view.source.id, DocumentRetrievalState.enabled
        )
        assert enabled.source.retrieval_state is DocumentRetrievalState.enabled
        with get_connection() as connection:
            assert connection.execute(
                "SELECT retrieval_state FROM documents WHERE id=%s", (document_id,)
            ).fetchone()[0] == "enabled"
            assert connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE document_id=%s",
                (document_id,),
            ).fetchone()[0] == job_count
    finally:
        _cleanup({document_id})
