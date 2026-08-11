import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from assistant.domain.assistant_behaviour import AssistantBehaviourRevision, AssistantBehaviourState
from assistant.domain.assistant_behaviour_repository import (
    AssistantBehaviourPublishConflict,
    AssistantBehaviourRepository,
    AssistantBehaviourUpdateConflict,
)
from core.metrics import assistant_behaviour_metrics

logger = logging.getLogger(__name__)


class AssistantBehaviourService:
    def __init__(
        self,
        repository: AssistantBehaviourRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository
        self.clock = clock

    def get_state(self, assistant_id: UUID) -> AssistantBehaviourState:
        return self.repository.get_state(assistant_id)

    def save_draft(
        self,
        assistant_id: UUID,
        *,
        concurrency_token: str,
        instructions: str,
        welcome_message: str,
        input_placeholder: str,
        suggested_questions: tuple[str, ...],
    ) -> AssistantBehaviourState:
        # Construct once at the domain boundary so invalid content never reaches persistence.
        current = self.repository.get_state(assistant_id)
        now = self.clock()
        AssistantBehaviourRevision(
            assistant_id,
            current.draft.revision + 1,
            instructions,
            welcome_message,
            input_placeholder,
            suggested_questions,
            now,
        )
        try:
            state = self.repository.save_draft(
                assistant_id,
                expected_token=concurrency_token,
                instructions=instructions,
                welcome_message=welcome_message,
                input_placeholder=input_placeholder,
                suggested_questions=suggested_questions,
                at=now,
            )
        except AssistantBehaviourUpdateConflict:
            self._record("save", "conflict", assistant_id)
            raise
        except Exception:
            self._record("save", "failure", assistant_id)
            raise
        self._record("save", "success", assistant_id, draft_revision=state.draft.revision)
        return state

    def publish(
        self,
        assistant_id: UUID,
        *,
        concurrency_token: str,
        draft_revision: int,
    ) -> AssistantBehaviourState:
        try:
            state = self.repository.publish(
                assistant_id,
                expected_token=concurrency_token,
                draft_revision=draft_revision,
                at=self.clock(),
            )
        except AssistantBehaviourPublishConflict:
            self._record("publish", "conflict", assistant_id, draft_revision=draft_revision)
            raise
        except Exception:
            self._record("publish", "failure", assistant_id, draft_revision=draft_revision)
            raise
        self._record(
            "publish",
            "success",
            assistant_id,
            draft_revision=state.draft.revision,
            published_revision=state.published.revision if state.published else None,
        )
        return state

    @staticmethod
    def _record(operation: str, outcome: str, assistant_id: UUID, **fields: object) -> None:
        try:
            assistant_behaviour_metrics.operations.labels(
                operation=operation, outcome=outcome
            ).inc()
        except Exception:
            pass
        try:
            logger.info(
                f"assistant_behaviour_{operation}_{outcome}",
                extra={"assistant_id": str(assistant_id), "outcome": outcome, **fields},
            )
        except Exception:
            pass
