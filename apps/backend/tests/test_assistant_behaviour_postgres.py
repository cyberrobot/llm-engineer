import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

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
        assert published.draft.revision == saved.draft.revision
        assert published.draft.created_at == saved.draft.created_at
        assert published.published_at != saved.published_at
        assert published.updated_at != saved.updated_at
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


def test_concurrent_draft_saves_from_same_token_have_exactly_one_winner() -> None:
    assistant = create_assistant(f"concurrent-save-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    initial = repository.get_state(assistant.id)
    barrier = Barrier(2)

    def save(instructions: str):
        barrier.wait(timeout=5)
        try:
            return repository.save_draft(
                assistant.id,
                expected_token=initial.concurrency_token,
                instructions=instructions,
                welcome_message="",
                input_placeholder="Ask",
                suggested_questions=(),
                at=initial.updated_at + timedelta(seconds=1),
            )
        except AssistantBehaviourUpdateConflict as exc:
            return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, ("Writer A", "Writer B")))
        winners = [item for item in results if not isinstance(item, Exception)]
        conflicts = [item for item in results if isinstance(item, AssistantBehaviourUpdateConflict)]
        assert len(winners) == len(conflicts) == 1
        final = repository.get_state(assistant.id)
        assert final.draft.revision == 2
        assert final.draft.instructions == winners[0].draft.instructions
        assert final.version == 2
        assert final.published is not None and final.published.revision == 1
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT revision,instructions FROM assistant_behaviour_revisions "
                "WHERE assistant_id=%s ORDER BY revision",
                (str(assistant.id),),
            ).fetchall()
        assert rows == [(1, initial.draft.instructions), (2, final.draft.instructions)]
    finally:
        cleanup(assistant)


def test_concurrent_publish_of_same_draft_is_idempotent_with_one_version_mutation() -> None:
    assistant = create_assistant(f"concurrent-publish-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    initial = repository.get_state(assistant.id)
    saved = repository.save_draft(
        assistant.id,
        expected_token=initial.concurrency_token,
        instructions="Publish once",
        welcome_message="",
        input_placeholder="Ask",
        suggested_questions=(),
        at=initial.updated_at + timedelta(seconds=1),
    )
    barrier = Barrier(2)

    def publish():
        barrier.wait(timeout=5)
        return repository.publish(
            assistant.id,
            expected_token=saved.concurrency_token,
            draft_revision=2,
            at=saved.updated_at + timedelta(seconds=1),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: publish(), range(2)))
        assert all(item.published is not None and item.published.revision == 2 for item in results)
        final = repository.get_state(assistant.id)
        assert final.draft.revision == final.published.revision == 2  # type: ignore[union-attr]
        assert final.version == 3
        with get_connection() as connection:
            assert connection.execute(
                "SELECT count(*) FROM assistant_behaviour_revisions WHERE assistant_id=%s",
                (str(assistant.id),),
            ).fetchone() == (2,)
    finally:
        cleanup(assistant)


def test_publish_rejects_draft_superseded_after_administrator_observed_it() -> None:
    assistant = create_assistant(f"superseded-publish-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    try:
        initial = repository.get_state(assistant.id)
        observed = repository.save_draft(
            assistant.id,
            expected_token=initial.concurrency_token,
            instructions="Observed revision two",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=(),
            at=initial.updated_at + timedelta(seconds=1),
        )
        newer = repository.save_draft(
            assistant.id,
            expected_token=observed.concurrency_token,
            instructions="Newer revision three",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=(),
            at=observed.updated_at + timedelta(seconds=1),
        )
        with pytest.raises(AssistantBehaviourPublishConflict):
            repository.publish(
                assistant.id,
                expected_token=observed.concurrency_token,
                draft_revision=observed.draft.revision,
                at=newer.updated_at + timedelta(seconds=1),
            )
        final = repository.get_state(assistant.id)
        assert final.draft.revision == 3
        assert final.published is not None and final.published.revision == 1
        assert final.version == 3
    finally:
        cleanup(assistant)


def _install_state_failure_trigger(assistant: Assistant, *, publication: bool) -> None:
    _drop_state_failure_trigger(publication=publication)
    operation = "publication" if publication else "draft"
    function_name = sql.Identifier(f"fail_test_behaviour_{operation}")
    trigger_name = sql.Identifier(f"fail_test_behaviour_{operation}")
    condition = (
        "OLD.published_revision IS DISTINCT FROM NEW.published_revision"
        if publication
        else "OLD.draft_revision IS DISTINCT FROM NEW.draft_revision"
    )
    with get_connection() as connection:
        connection.execute(
            sql.SQL(
                "CREATE OR REPLACE FUNCTION {}() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced behaviour failure'; END $$"
            ).format(function_name)
        )
        connection.execute(
            sql.SQL(
                "CREATE TRIGGER {} BEFORE UPDATE ON "
                "assistant_behaviour_states FOR EACH ROW WHEN (OLD.assistant_id = {} AND {}) "
                "EXECUTE FUNCTION {}()"
            ).format(
                trigger_name,
                sql.Literal(str(assistant.id)),
                sql.SQL(condition),
                function_name,
            )
        )


def _drop_state_failure_trigger(*, publication: bool) -> None:
    operation = "publication" if publication else "draft"
    object_name = sql.Identifier(f"fail_test_behaviour_{operation}")
    with get_connection() as connection:
        connection.execute(
            sql.SQL("DROP TRIGGER IF EXISTS {} ON assistant_behaviour_states").format(object_name)
        )
        connection.execute(sql.SQL("DROP FUNCTION IF EXISTS {}()").format(object_name))


def test_failed_state_update_rolls_back_inserted_draft_revision() -> None:
    assistant = create_assistant(f"draft-rollback-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    initial = repository.get_state(assistant.id)
    try:
        _install_state_failure_trigger(assistant, publication=False)
        with pytest.raises(psycopg.errors.RaiseException, match="forced behaviour failure"):
            repository.save_draft(
                assistant.id,
                expected_token=initial.concurrency_token,
                instructions="Must roll back",
                welcome_message="",
                input_placeholder="Ask",
                suggested_questions=(),
                at=initial.updated_at + timedelta(seconds=1),
            )
        assert repository.get_state(assistant.id) == initial
        with get_connection() as connection:
            assert connection.execute(
                "SELECT count(*) FROM assistant_behaviour_revisions "
                "WHERE assistant_id=%s AND revision=2",
                (str(assistant.id),),
            ).fetchone() == (0,)
    finally:
        _drop_state_failure_trigger(publication=False)
        cleanup(assistant)


def test_failed_publication_rolls_back_pointer_timestamp_and_version() -> None:
    assistant = create_assistant(f"publish-rollback-{uuid4().hex}")
    repository = PostgresAssistantBehaviourRepository()
    initial = repository.get_state(assistant.id)
    saved = repository.save_draft(
        assistant.id,
        expected_token=initial.concurrency_token,
        instructions="Draft two",
        welcome_message="",
        input_placeholder="Ask",
        suggested_questions=(),
        at=initial.updated_at + timedelta(seconds=1),
    )
    try:
        _install_state_failure_trigger(assistant, publication=True)
        with pytest.raises(psycopg.errors.RaiseException, match="forced behaviour failure"):
            repository.publish(
                assistant.id,
                expected_token=saved.concurrency_token,
                draft_revision=2,
                at=saved.updated_at + timedelta(seconds=1),
            )
        assert repository.get_state(assistant.id) == saved
    finally:
        _drop_state_failure_trigger(publication=True)
        cleanup(assistant)


def test_failed_behaviour_initialization_rolls_back_assistant_and_retry_succeeds() -> None:
    assistant = Assistant(
        uuid4(),
        f"create-rollback-{uuid4().hex}",
        "Create rollback",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        datetime(2026, 8, 11, tzinfo=timezone.utc),
        datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    with get_connection() as connection:
        connection.execute(
            "DROP TRIGGER IF EXISTS fail_test_behaviour_initialization "
            "ON assistant_behaviour_revisions"
        )
        connection.execute("DROP FUNCTION IF EXISTS fail_test_behaviour_initialization()")
        connection.execute(
            "CREATE OR REPLACE FUNCTION fail_test_behaviour_initialization() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced initialization failure'; END $$"
        )
        connection.execute(
            sql.SQL(
                "CREATE TRIGGER fail_test_behaviour_initialization BEFORE INSERT ON "
                "assistant_behaviour_revisions FOR EACH ROW WHEN (NEW.assistant_id = {}) "
                "EXECUTE FUNCTION fail_test_behaviour_initialization()"
            ).format(sql.Literal(str(assistant.id)))
        )
    try:
        with pytest.raises(psycopg.errors.RaiseException, match="forced initialization failure"):
            PostgresAssistantRepository().create(assistant)
        with get_connection() as connection:
            assert connection.execute(
                "SELECT count(*) FROM assistants WHERE id=%s", (str(assistant.id),)
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM assistant_behaviour_revisions WHERE assistant_id=%s",
                (str(assistant.id),),
            ).fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM assistant_behaviour_states WHERE assistant_id=%s",
                (str(assistant.id),),
            ).fetchone() == (0,)
        with get_connection() as connection:
            connection.execute(
                "DROP TRIGGER fail_test_behaviour_initialization ON assistant_behaviour_revisions"
            )
            connection.execute("DROP FUNCTION fail_test_behaviour_initialization()")
        assert PostgresAssistantRepository().create(assistant) == assistant
        assert PostgresAssistantBehaviourRepository().get_state(assistant.id).draft.revision == 1
    finally:
        with get_connection() as connection:
            connection.execute(
                "DROP TRIGGER IF EXISTS fail_test_behaviour_initialization "
                "ON assistant_behaviour_revisions"
            )
            connection.execute("DROP FUNCTION IF EXISTS fail_test_behaviour_initialization()")
        cleanup(assistant)


def test_database_rejects_revision_mutation_referenced_deletion_and_unsafe_questions() -> None:
    assistant = create_assistant(f"immutable-{uuid4().hex}")
    try:
        with get_connection() as connection:
            connection.execute("SAVEPOINT revision_update")
            with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
                connection.execute(
                    "UPDATE assistant_behaviour_revisions SET instructions='changed' "
                    "WHERE assistant_id=%s AND revision=1",
                    (str(assistant.id),),
                )
            connection.execute("ROLLBACK TO SAVEPOINT revision_update")
            assert (
                connection.execute(
                    "SELECT instructions FROM assistant_behaviour_revisions "
                    "WHERE assistant_id=%s AND revision=1",
                    (str(assistant.id),),
                ).fetchone()[0]
                != "changed"
            )

            connection.execute("SAVEPOINT revision_delete")
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(
                    "DELETE FROM assistant_behaviour_revisions WHERE assistant_id=%s AND revision=1",
                    (str(assistant.id),),
                )
            connection.execute("ROLLBACK TO SAVEPOINT revision_delete")

            connection.execute("SAVEPOINT unsafe_question")
            with pytest.raises(psycopg.errors.RaiseException, match="invalid suggested question"):
                connection.execute(
                    """INSERT INTO assistant_behaviour_revisions
                       (assistant_id,revision,instructions,welcome_message,input_placeholder,
                        suggested_questions,created_at)
                       VALUES (%s,2,'Safe','','Ask','[\"tab\\tquestion\"]'::jsonb,NOW())""",
                    (str(assistant.id),),
                )
            connection.execute("ROLLBACK TO SAVEPOINT unsafe_question")
    finally:
        cleanup(assistant)
