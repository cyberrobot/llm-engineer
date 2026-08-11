import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_behaviour_repository import (
    AssistantBehaviourPublishConflict,
    AssistantBehaviourUpdateConflict,
)
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from assistant.infrastructure.repositories.assistant_behaviour import (
    PostgresAssistantBehaviourRepository,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db


def _require_database() -> None:
    required = (
        os.getenv("ASSISTANT_BEHAVIOUR_POSTGRES_REQUIRED") == "true" or os.getenv("CI") == "true"
    )
    if not DATABASE_URL:
        if required:
            pytest.fail("DATABASE_URL is required for Assistant behaviour PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if required:
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


@pytest.fixture(autouse=True)
def database() -> None:
    _require_database()
    init_db()


def create_assistant(slug: str) -> Assistant:
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    assistant = Assistant(
        uuid4(), slug, slug.title(), AssistantStatus.inactive, AssistantVisibility.private, now, now
    )
    PostgresAssistantRepository().create(assistant)
    return assistant


def cleanup(*assistants: Assistant) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM assistants WHERE id = ANY(%s)",
            ([str(item.id) for item in assistants],),
        )


def test_new_assistant_has_default_published_state_and_revision_updates_are_isolated() -> None:
    assistant = create_assistant(f"behaviour-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    try:
        initial = repository.get_state(assistant.id)
        assert initial.draft.revision == 1
        assert initial.published == initial.draft
        saved = repository.save_draft(
            assistant.id,
            expected_token=initial.concurrency_token,
            instructions="A new saved draft",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=("Question?",),
            at=initial.updated_at + timedelta(seconds=1),
        )
        assert saved.draft.revision == 2
        assert repository.get_published(assistant.id).revision == 1
        with pytest.raises(AssistantBehaviourUpdateConflict):
            repository.save_draft(
                assistant.id,
                expected_token=initial.concurrency_token,
                instructions="Stale",
                welcome_message="",
                input_placeholder="Ask",
                suggested_questions=(),
                at=saved.updated_at + timedelta(seconds=1),
            )
        assert repository.get_state(assistant.id) == saved
    finally:
        cleanup(assistant)


def test_publish_exact_revision_and_database_rejects_cross_assistant_pointer() -> None:
    first = create_assistant(f"first-{uuid4().hex}")
    second = create_assistant(f"second-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    try:
        initial = repository.get_state(first.id)
        saved = repository.save_draft(
            first.id,
            expected_token=initial.concurrency_token,
            instructions="First draft two",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=(),
            at=initial.updated_at + timedelta(seconds=1),
        )
        with pytest.raises(AssistantBehaviourPublishConflict):
            repository.publish(
                first.id,
                expected_token=saved.concurrency_token,
                draft_revision=1,
                at=saved.updated_at + timedelta(seconds=1),
            )
        published = repository.publish(
            first.id,
            expected_token=saved.concurrency_token,
            draft_revision=2,
            at=saved.updated_at + timedelta(seconds=1),
        )
        assert published.published is not None and published.published.revision == 2
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with get_connection() as connection:
                connection.execute(
                    "UPDATE assistant_behaviour_states SET published_revision=2 WHERE assistant_id=%s",
                    (str(second.id),),
                )
    finally:
        cleanup(first, second)


def test_deleting_unused_assistant_cascades_exclusive_behaviour() -> None:
    assistant = create_assistant(f"delete-{uuid4().hex}")
    PostgresAssistantRepository().delete(assistant.id)
    with get_connection() as connection:
        state_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_behaviour_states WHERE assistant_id=%s",
            (str(assistant.id),),
        ).fetchone()[0]
        revision_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_behaviour_revisions WHERE assistant_id=%s",
            (str(assistant.id),),
        ).fetchone()[0]
    assert (state_count, revision_count) == (0, 0)
