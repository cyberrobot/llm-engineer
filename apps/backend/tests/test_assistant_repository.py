from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import (
    AssistantNotFound,
    DuplicateAssistantSlug,
)
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository


def repository_with_row(row):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    connection = MagicMock()
    connection.cursor.return_value = nullcontext(cursor)
    return PostgresAssistantRepository(lambda: nullcontext(connection)), cursor


def test_assistant_repository_looks_up_by_id_and_slug():
    assistant_id = uuid4()
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    row = (assistant_id, "reviewer", "Reviewer", "active", "private", now, now)

    by_id, id_cursor = repository_with_row(row)
    by_slug, slug_cursor = repository_with_row(row)

    assert by_id.get_by_id(assistant_id).status is AssistantStatus.active
    assert by_slug.get_by_slug(" reviewer ").visibility is AssistantVisibility.private
    assert id_cursor.execute.call_args.args[1] == (str(assistant_id),)
    assert slug_cursor.execute.call_args.args[1] == ("reviewer",)


def test_assistant_repository_uses_safe_not_found_error():
    repository, _cursor = repository_with_row(None)

    with pytest.raises(AssistantNotFound, match="Assistant not found"):
        repository.get_by_slug("missing")

    with pytest.raises(AssistantNotFound, match="Assistant not found"):
        repository.get_by_slug("  ")


class _Diagnostic:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class _UniqueFailure(Exception):
    sqlstate = "23505"

    def __init__(self, constraint_name: str) -> None:
        self.diag = _Diagnostic(constraint_name)


def _failing_repository(constraint_name: str) -> PostgresAssistantRepository:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            raise _UniqueFailure(constraint_name)

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    return PostgresAssistantRepository(connection)


def _assistant_for_create() -> Assistant:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    return Assistant(
        uuid4(),
        "reviewer",
        "Reviewer",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        now,
        now,
    )


def test_only_the_slug_constraint_maps_to_duplicate_slug():
    with pytest.raises(DuplicateAssistantSlug):
        _failing_repository("assistants_slug_key").create(_assistant_for_create())


def test_duplicate_id_is_not_mislabeled_as_a_slug_conflict():
    with pytest.raises(_UniqueFailure) as raised:
        _failing_repository("assistants_pkey").create(_assistant_for_create())
    assert not isinstance(raised.value, DuplicateAssistantSlug)
