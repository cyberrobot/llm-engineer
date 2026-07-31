from datetime import datetime, timezone
from uuid import uuid4

import pytest

from assistant.domain.assistant import (
    REDMOOR_ASSISTANT_ID,
    REDMOOR_ASSISTANT_SLUG,
    Assistant,
    AssistantStatus,
    AssistantVisibility,
    DocumentRetrievalState,
)


def test_assistant_represents_independent_status_and_visibility():
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)

    assistant = Assistant(
        id=uuid4(),
        slug="internal-reviewer",
        name="Internal Reviewer",
        status=AssistantStatus.active,
        visibility=AssistantVisibility.private,
        created_at=now,
        updated_at=now,
    )

    assert assistant.status is AssistantStatus.active
    assert assistant.visibility is AssistantVisibility.private
    assert REDMOOR_ASSISTANT_SLUG == "redmoor"
    assert str(REDMOOR_ASSISTANT_ID) == "f338bb74-5d44-5165-9041-090d5c593a68"


@pytest.mark.parametrize(
    ("enum_type", "unsupported"),
    [
        (AssistantStatus, "paused"),
        (AssistantVisibility, "external"),
        (DocumentRetrievalState, "archived"),
    ],
)
def test_assistant_domain_values_reject_unsupported_strings(enum_type, unsupported):
    with pytest.raises(ValueError):
        enum_type(unsupported)


def test_document_retrieval_state_has_enabled_and_disabled_values():
    assert {state.value for state in DocumentRetrievalState} == {"enabled", "disabled"}


@pytest.mark.parametrize("slug", ["", "Has Spaces", "UPPERCASE", "unsafe/path"])
def test_assistant_rejects_invalid_slug(slug):
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="slug"):
        Assistant(
            id=uuid4(),
            slug=slug,
            name="Assistant",
            status=AssistantStatus.active,
            visibility=AssistantVisibility.public,
            created_at=now,
            updated_at=now,
        )
