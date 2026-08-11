from datetime import datetime
from typing import Protocol
from uuid import UUID

from assistant.domain.assistant_behaviour import AssistantBehaviourRevision, AssistantBehaviourState


class AssistantBehaviourNotFound(LookupError):
    pass


class AssistantBehaviourUpdateConflict(RuntimeError):
    pass


class AssistantBehaviourPublishConflict(RuntimeError):
    pass


class AssistantBehaviourRepository(Protocol):
    def get_state(self, assistant_id: UUID) -> AssistantBehaviourState: ...
    def get_published(self, assistant_id: UUID) -> AssistantBehaviourRevision: ...
    def save_draft(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        instructions: str,
        welcome_message: str,
        input_placeholder: str,
        suggested_questions: tuple[str, ...],
        at: datetime,
    ) -> AssistantBehaviourState: ...
    def publish(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        draft_revision: int,
        at: datetime,
    ) -> AssistantBehaviourState: ...
