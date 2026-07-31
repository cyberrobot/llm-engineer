from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from assistant.domain.assistant import AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import AssistantNotFound
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
