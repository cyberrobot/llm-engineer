from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from assistant.application.ingestion_job_service import DocumentIngestionJobService
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.infrastructure.repositories.document_ingestion_job import (
    PostgresDocumentIngestionJobRepository,
)
from assistant.infrastructure.repositories.ingestion_worker import (
    FencedPostgresDocumentIngestionJobRepository,
    IngestionOwnershipLost,
    PostgresIngestionWorkerRepository,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def create_document(document_id: str, created_at: datetime) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, doc_type, source_url, assistant_id)
            VALUES (%s, 'test', %s, %s)
            """,
            (document_id, f"https://example.com/{document_id}", str(REDMOOR_ASSISTANT_ID)),
        )
    repository = PostgresDocumentIngestionJobRepository()
    DocumentIngestionJobService(repository).create(document_id)
    with get_connection() as connection:
        connection.execute(
            "UPDATE document_ingestion_jobs SET created_at = %s, updated_at = %s "
            "WHERE document_id = %s",
            (created_at, created_at, document_id),
        )


def cleanup(document_ids: list[str]) -> None:
    with suppress(Exception), get_connection() as connection:
        connection.execute("DELETE FROM documents WHERE id = ANY(%s)", (document_ids,))


def test_two_postgres_claimers_distribute_jobs_without_duplication():
    require_database()
    init_db()
    document_ids = [str(uuid4()), str(uuid4())]
    for offset, document_id in enumerate(document_ids):
        create_document(document_id, NOW + timedelta(seconds=offset))

    def claim(worker_id):
        return PostgresIngestionWorkerRepository().claim_next(
            worker_id, timedelta(seconds=60), NOW + timedelta(seconds=2)
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(claim, ("worker-a", "worker-b")))

        assert all(claims)
        assert len({claim.job_id for claim in claims if claim}) == 2
        assert {claim.worker_id for claim in claims if claim} == {"worker-a", "worker-b"}
    finally:
        cleanup(document_ids)


def test_expired_claim_is_recovered_once_and_stale_worker_cannot_complete():
    require_database()
    init_db()
    document_id = str(uuid4())
    create_document(document_id, NOW)
    worker_repository = PostgresIngestionWorkerRepository()

    try:
        job = PostgresDocumentIngestionJobRepository().list(
            limit=1, offset=0, document_id=document_id
        )
        assert len(job.items) == 1
        job_id = job.items[0].id
        first = worker_repository.claim_job(job_id, "worker-a", timedelta(seconds=1), NOW)
        assert first
        second = worker_repository.claim_job(
            job_id, "worker-b", timedelta(seconds=60), NOW + timedelta(seconds=2)
        )
        assert second
        assert second.job_id == first.job_id
        assert second.recovered
        assert second.claim_version == first.claim_version + 1

        stale_repository = FencedPostgresDocumentIngestionJobRepository(first)
        stale = stale_repository.get_by_id(first.job_id)
        assert stale
        stale.mark_completed(at=NOW + timedelta(seconds=3))
        with pytest.raises(IngestionOwnershipLost):
            stale_repository.update(stale)

        assert (
            worker_repository.claim_job(
                job_id, "worker-c", timedelta(seconds=60), NOW + timedelta(seconds=3)
            )
            is None
        )
    finally:
        cleanup([document_id])


def test_heartbeat_extends_only_the_current_unexpired_claim():
    require_database()
    init_db()
    document_id = str(uuid4())
    create_document(document_id, NOW)
    repository = PostgresIngestionWorkerRepository()

    try:
        claim = repository.claim_next("worker-a", timedelta(seconds=10), NOW)
        assert claim
        assert repository.renew_lease(claim, timedelta(seconds=10), NOW + timedelta(seconds=5))
        assert not repository.renew_lease(claim, timedelta(seconds=10), NOW + timedelta(seconds=16))
    finally:
        cleanup([document_id])
