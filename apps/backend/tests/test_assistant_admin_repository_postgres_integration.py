import os
from datetime import datetime, timedelta, timezone
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
        page, total = repository.list(limit=2, offset=0)
        assert total >= 2
        assert page.index(second) < page.index(first)
        filtered, filtered_total = repository.list(
            limit=100,
            offset=0,
            status=AssistantStatus.active,
            visibility=AssistantVisibility.public,
        )
        assert second in filtered
        assert first not in filtered
        assert filtered_total == len(filtered)
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
