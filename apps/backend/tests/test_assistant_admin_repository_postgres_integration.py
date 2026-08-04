import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import psycopg
import pytest

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import (
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    AssistantNotFound,
    DuplicateAssistantSlug,
)
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db


def _require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("ASSISTANT_ADMIN_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for assistant administrator PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("ASSISTANT_ADMIN_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


@pytest.fixture(autouse=True)
def database() -> None:
    _require_database()
    init_db()


def _assistant(
    *,
    slug: str,
    created_at: datetime,
    status: AssistantStatus = AssistantStatus.inactive,
    visibility: AssistantVisibility = AssistantVisibility.private,
) -> Assistant:
    return Assistant(uuid4(), slug, slug.title(), status, visibility, created_at, created_at)


def _cleanup(*assistants: Assistant) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM assistants WHERE id = ANY(%s)",
            ([str(assistant.id) for assistant in assistants],),
        )


def test_postgres_creation_lookup_defaults_filters_ordering_and_count() -> None:
    repository = PostgresAssistantRepository()
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    first = _assistant(slug=f"first-{uuid4().hex}", created_at=now)
    second = _assistant(
        slug=f"second-{uuid4().hex}",
        created_at=now + timedelta(seconds=1),
        status=AssistantStatus.active,
        visibility=AssistantVisibility.public,
    )
    try:
        repository.create(first)
        repository.create(second)
        assert repository.get_by_id(first.id) == first
        assert repository.get_by_slug(second.slug) == second
        page, total = repository.list(limit=100, offset=0)
        assert total >= 2
        created_page = [item for item in page if item.id in {first.id, second.id}]
        assert created_page == [second, first]
        filtered, filtered_total = repository.list(
            limit=100,
            offset=0,
            status=AssistantStatus.active,
            visibility=AssistantVisibility.public,
        )
        assert second in filtered
        assert first not in filtered
        assert filtered_total >= len(filtered)
    finally:
        _cleanup(first, second)


def test_postgres_unique_slug_and_duplicate_id_are_distinct() -> None:
    repository = PostgresAssistantRepository()
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    original = _assistant(slug=f"unique-{uuid4().hex}", created_at=now)
    same_slug = Assistant(
        uuid4(),
        original.slug,
        "Other",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        now,
        now,
    )
    same_id = Assistant(
        original.id,
        f"different-{uuid4().hex}",
        "Other",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        now,
        now,
    )
    try:
        repository.create(original)
        with pytest.raises(DuplicateAssistantSlug):
            repository.create(same_slug)
        with pytest.raises(psycopg.errors.UniqueViolation) as duplicate_id:
            repository.create(same_id)
        assert duplicate_id.value.diag.constraint_name == "assistants_pkey"
    finally:
        _cleanup(original, same_slug)


def test_postgres_timestamp_compare_and_set_tokens_are_distinct_and_reusable() -> None:
    repository = PostgresAssistantRepository()
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    original = _assistant(slug=f"token-{uuid4().hex}", created_at=now)
    try:
        repository.create(original)
        first = original.rename("First", at=now + timedelta(microseconds=1))
        assert repository.update(first, expected_updated_at=original.updated_at) == first
        round_tripped = repository.get_by_id(original.id)
        second = round_tripped.rename(
            "Second", at=round_tripped.updated_at + timedelta(microseconds=1)
        )
        assert repository.update(second, expected_updated_at=round_tripped.updated_at) == second
        assert second.updated_at > first.updated_at
        with pytest.raises(AssistantConcurrentUpdate):
            repository.update(first.rename("Stale", at=second.updated_at), expected_updated_at=now)
    finally:
        _cleanup(original)


def test_postgres_dependency_summary_blocks_delete_and_unused_delete_succeeds() -> None:
    repository = PostgresAssistantRepository()
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    dependent = _assistant(slug=f"dependent-{uuid4().hex}", created_at=now)
    unused = _assistant(slug=f"unused-{uuid4().hex}", created_at=now)
    document_id = str(uuid4())
    try:
        repository.create(dependent)
        repository.create(unused)
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO documents (id,doc_type,assistant_id) VALUES (%s,'text',%s)",
                (document_id, str(dependent.id)),
            )
        assert repository.has_dependencies(dependent.id) is True
        with pytest.raises(AssistantDeletionBlocked):
            repository.delete(dependent.id)
        assert repository.get_by_id(dependent.id) == dependent
        repository.delete(unused.id)
        with pytest.raises(AssistantNotFound):
            repository.get_by_id(unused.id)
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        _cleanup(dependent, unused)


def test_postgres_pagination_is_deterministic_for_test_created_rows() -> None:
    repository = PostgresAssistantRepository()
    stamp = datetime(2099, 1, 1, tzinfo=timezone.utc)
    prefix = uuid4().hex
    ids = sorted((uuid4(), uuid4(), uuid4()), reverse=True)
    assistants = [
        Assistant(
            assistant_id,
            f"page-{prefix}-{index}",
            f"Page {index}",
            AssistantStatus.inactive,
            AssistantVisibility.private,
            stamp,
            stamp,
        )
        for index, assistant_id in enumerate(ids)
    ]
    try:
        for item in assistants:
            repository.create(item)
        page, total = repository.list(
            limit=2,
            offset=0,
            status=AssistantStatus.inactive,
            visibility=AssistantVisibility.private,
        )
        created = [item for item in page if item.id in set(ids)]
        assert created == assistants[:2]
        assert total >= 3
        next_page, same_total = repository.list(
            limit=1,
            offset=2,
            status=AssistantStatus.inactive,
            visibility=AssistantVisibility.private,
        )
        assert same_total == total
        assert next_page[0] == assistants[2]
        empty, empty_total = repository.list(
            limit=10,
            offset=0,
            status=AssistantStatus.active,
            visibility=AssistantVisibility.private,
        )
        assert all(item.id not in set(ids) for item in empty)
        assert empty_total >= len(empty)
    finally:
        _cleanup(*assistants)


def test_concurrent_dependent_insert_cannot_commit_after_assistant_delete() -> None:
    assert DATABASE_URL is not None
    database_url = DATABASE_URL
    repository = PostgresAssistantRepository()
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    target = _assistant(slug=f"race-{uuid4().hex}", created_at=now)
    document_id = str(uuid4())
    locked = Event()
    insert_started = Event()
    release_delete = Event()
    repository.create(target)

    def delete_transaction() -> None:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute("SELECT 1 FROM assistants WHERE id=%s FOR UPDATE", (str(target.id),))
            assert cursor.fetchone() == (1,)
            locked.set()
            assert release_delete.wait(5), "dependent insert did not start in time"
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM knowledge_sources WHERE assistant_id=%s "
                "UNION ALL SELECT 1 FROM documents WHERE assistant_id=%s "
                "UNION ALL SELECT 1 FROM chunks WHERE assistant_id=%s)",
                (str(target.id),) * 3,
            )
            assert cursor.fetchone() == (False,)
            cursor.execute("DELETE FROM assistants WHERE id=%s", (str(target.id),))

    def insert_transaction() -> str:
        assert locked.wait(5), "delete transaction did not acquire its row lock"
        insert_started.set()
        try:
            with psycopg.connect(database_url) as connection:
                connection.execute("SET LOCAL statement_timeout = '5s'")
                connection.execute(
                    "INSERT INTO documents (id,doc_type,assistant_id) VALUES (%s,'text',%s)",
                    (document_id, str(target.id)),
                )
            return "committed"
        except psycopg.errors.ForeignKeyViolation:
            return "foreign_key_rejected"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            deleted = executor.submit(delete_transaction)
            inserted = executor.submit(insert_transaction)
            assert insert_started.wait(5), "dependent insert thread did not start"
            release_delete.set()
            try:
                deleted.result(timeout=10)
                outcome = inserted.result(timeout=10)
            except FutureTimeout as exc:
                pytest.fail(f"concurrent delete/insert did not finish: {exc}")
        assert outcome == "foreign_key_rejected"
        with get_connection() as connection:
            assert connection.execute(
                "SELECT count(*) FROM assistants WHERE id=%s", (str(target.id),)
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM documents WHERE id=%s", (document_id,)
            ).fetchone() == (0,)
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        _cleanup(target)


def test_delete_database_failure_rolls_back_and_connection_remains_usable() -> None:
    repository = PostgresAssistantRepository()
    target = _assistant(
        slug=f"rollback-{uuid4().hex}", created_at=datetime(2026, 8, 4, tzinfo=timezone.utc)
    )
    repository.create(target)
    try:
        with get_connection() as connection:
            connection.execute(
                "CREATE OR REPLACE FUNCTION fail_test_assistant_delete() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced delete failure'; END $$"
            )
            connection.execute(
                "CREATE TRIGGER fail_test_assistant_delete BEFORE DELETE ON assistants "
                "FOR EACH ROW EXECUTE FUNCTION fail_test_assistant_delete()"
            )
        with pytest.raises(psycopg.errors.RaiseException, match="forced delete failure"):
            repository.delete(target.id)
        assert repository.get_by_id(target.id) == target
        assert repository.list(limit=1, offset=0)[1] >= 1
    finally:
        with get_connection() as connection:
            connection.execute("DROP TRIGGER IF EXISTS fail_test_assistant_delete ON assistants")
            connection.execute("DROP FUNCTION IF EXISTS fail_test_assistant_delete()")
        _cleanup(target)


def test_indirect_ingestion_records_are_covered_by_document_parent_dependency() -> None:
    repository = PostgresAssistantRepository()
    target = _assistant(
        slug=f"indirect-{uuid4().hex}", created_at=datetime(2026, 8, 4, tzinfo=timezone.utc)
    )
    document_id, job_id = str(uuid4()), str(uuid4())
    repository.create(target)
    try:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO documents (id,doc_type,assistant_id) VALUES (%s,'text',%s)",
                (document_id, str(target.id)),
            )
            connection.execute(
                "INSERT INTO document_ingestion_jobs (id,document_id,status,progress) "
                "VALUES (%s,%s,'queued',0)",
                (job_id, document_id),
            )
            connection.execute(
                "INSERT INTO ingestion_step_executions "
                "(ingestion_job_id,step,attempt_number,status,started_at) "
                "VALUES (%s,'parse',1,'running',NOW())",
                (job_id,),
            )
        summary = repository.dependency_summary(target.id)
        assert summary.has_dependencies is True
        with pytest.raises(AssistantDeletionBlocked):
            repository.delete(target.id)
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM ingestion_step_executions WHERE ingestion_job_id=%s", (job_id,)
            )
        assert repository.dependency_summary(target.id).has_dependencies is True
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
            assert connection.execute(
                "SELECT count(*) FROM document_ingestion_jobs WHERE id=%s", (job_id,)
            ).fetchone() == (0,)
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    "INSERT INTO ingestion_step_executions "
                    "(ingestion_job_id,step,attempt_number,status,started_at) "
                    "VALUES (%s,'parse',1,'running',NOW())",
                    (job_id,),
                )
        repository.delete(target.id)
    finally:
        with get_connection() as connection:
            connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        _cleanup(target)
