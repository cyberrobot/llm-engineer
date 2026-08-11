from datetime import datetime, timezone
from uuid import uuid4

import pytest

from assistant.domain.assistant_behaviour import (
    MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH,
    MAX_INPUT_PLACEHOLDER_LENGTH,
    MAX_SUGGESTED_QUESTION_LENGTH,
    MAX_SUGGESTED_QUESTIONS,
    MAX_WELCOME_MESSAGE_LENGTH,
    AssistantBehaviourRevision,
    AssistantBehaviourState,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def revision(**changes: object) -> AssistantBehaviourRevision:
    values = {
        "assistant_id": uuid4(),
        "revision": 1,
        "instructions": "  Keep this whitespace.\nBe friendly.  ",
        "welcome_message": "Welcome",
        "input_placeholder": "Ask a question",
        "suggested_questions": ("First?", "Second?"),
        "created_at": NOW,
    }
    values.update(changes)
    return AssistantBehaviourRevision(**values)  # type: ignore[arg-type]


def test_valid_behaviour_preserves_whitespace_unicode_and_question_order() -> None:
    result = revision(instructions="  Répondre clairement.\n  ")
    assert result.instructions == "  Répondre clairement.\n  "
    assert result.suggested_questions == ("First?", "Second?")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("instructions", " \n\t "),
        ("instructions", "x" * (MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH + 1)),
        ("instructions", "unsafe\x00"),
        ("welcome_message", "x" * (MAX_WELCOME_MESSAGE_LENGTH + 1)),
        ("welcome_message", "unsafe\x01"),
        ("input_placeholder", "x" * (MAX_INPUT_PLACEHOLDER_LENGTH + 1)),
        ("input_placeholder", "two\nlines"),
        ("suggested_questions", ("x" * (MAX_SUGGESTED_QUESTION_LENGTH + 1),)),
        ("suggested_questions", ("  ",)),
        ("suggested_questions", ("two\nlines",)),
        ("suggested_questions", tuple("question" for _ in range(MAX_SUGGESTED_QUESTIONS + 1))),
        ("revision", 0),
    ],
)
def test_invalid_behaviour_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        revision(**{field: value})


def test_publication_state_calculates_unpublished_changes_and_ownership() -> None:
    draft = revision()
    published = revision(assistant_id=draft.assistant_id)
    state = AssistantBehaviourState(draft.assistant_id, draft, published, NOW, 1, NOW)
    assert state.has_unpublished_changes is False
    assert state.concurrency_token == "1"

    newer = revision(assistant_id=draft.assistant_id, revision=2)
    assert AssistantBehaviourState(
        draft.assistant_id, newer, published, NOW, 2, NOW
    ).has_unpublished_changes
    with pytest.raises(ValueError, match="another Assistant"):
        AssistantBehaviourState(draft.assistant_id, revision(), published, NOW, 1, NOW)
