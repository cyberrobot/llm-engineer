from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from assistant.application.assistant_behaviour_service import AssistantBehaviourService
from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_behaviour_repository import (
    AssistantBehaviourPublishConflict,
    AssistantBehaviourUpdateConflict,
)
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from assistant.infrastructure.repositories.assistant_behaviour import (
    InMemoryAssistantBehaviourRepository,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def repository():
    assistant = Assistant(
        uuid4(),
        "preview",
        "Preview",
        AssistantStatus.inactive,
        AssistantVisibility.private,
        NOW,
        NOW,
    )
    assistants = InMemoryAssistantRepository((assistant,))
    return assistant, assistants, InMemoryAssistantBehaviourRepository(assistants)


def test_save_is_immutable_deduplicated_and_does_not_publish() -> None:
    assistant, _assistants, behaviours = repository()
    initial = behaviours.get_state(assistant.id)
    unchanged = behaviours.save_draft(
        assistant.id,
        expected_token=initial.concurrency_token,
        instructions=initial.draft.instructions,
        welcome_message=initial.draft.welcome_message,
        input_placeholder=initial.draft.input_placeholder,
        suggested_questions=initial.draft.suggested_questions,
        at=NOW + timedelta(seconds=1),
    )
    assert unchanged is initial

    saved = behaviours.save_draft(
        assistant.id,
        expected_token=initial.concurrency_token,
        instructions="New draft",
        welcome_message="New welcome",
        input_placeholder="Ask",
        suggested_questions=("Why?", "How?"),
        at=NOW + timedelta(seconds=2),
    )
    assert saved.draft.revision == 2
    assert saved.published is not None and saved.published.revision == 1
    assert saved.has_unpublished_changes
    assert behaviours.get_published(assistant.id).instructions == initial.draft.instructions
    with pytest.raises(AssistantBehaviourUpdateConflict):
        behaviours.save_draft(
            assistant.id,
            expected_token=initial.concurrency_token,
            instructions="Stale",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=(),
            at=NOW + timedelta(seconds=3),
        )


def test_publish_targets_exact_draft_and_is_idempotent() -> None:
    assistant, _assistants, behaviours = repository()
    initial = behaviours.get_state(assistant.id)
    saved = behaviours.save_draft(
        assistant.id,
        expected_token=initial.concurrency_token,
        instructions="Publish me",
        welcome_message="",
        input_placeholder="Ask",
        suggested_questions=(),
        at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(AssistantBehaviourPublishConflict):
        behaviours.publish(
            assistant.id,
            expected_token=saved.concurrency_token,
            draft_revision=1,
            at=NOW + timedelta(seconds=2),
        )
    published = behaviours.publish(
        assistant.id,
        expected_token=saved.concurrency_token,
        draft_revision=2,
        at=NOW + timedelta(seconds=2),
    )
    assert published.published == published.draft
    assert published.has_unpublished_changes is False
    assert (
        behaviours.publish(
            assistant.id,
            expected_token=saved.concurrency_token,
            draft_revision=2,
            at=NOW + timedelta(seconds=3),
        )
        == published
    )


@pytest.mark.parametrize("unsafe_question", ("tab\tquestion", "zero-width\u200bquestion"))
def test_service_rejects_unsafe_suggested_questions_before_persistence(
    unsafe_question: str,
) -> None:
    assistant, _assistants, behaviours = repository()

    class TrackingRepository:
        save_called = False

        def get_state(self, assistant_id):
            return behaviours.get_state(assistant_id)

        def save_draft(self, *args, **kwargs):
            del args, kwargs
            self.save_called = True
            raise AssertionError("unsafe content must not reach persistence")

    tracking = TrackingRepository()
    service = AssistantBehaviourService(tracking)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="one safe line"):
        service.save_draft(
            assistant.id,
            concurrency_token="1",
            instructions="Safe",
            welcome_message="",
            input_placeholder="Ask",
            suggested_questions=(unsafe_question,),
        )
    assert tracking.save_called is False
