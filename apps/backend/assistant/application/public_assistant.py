from dataclasses import dataclass

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourRepository
from assistant.domain.assistant_repository import AssistantNotFound, AssistantRepository


def require_publicly_available(assistant: Assistant) -> Assistant:
    """Apply the shared fail-closed availability boundary for anonymous callers."""
    if (
        assistant.status is not AssistantStatus.active
        or assistant.visibility is not AssistantVisibility.public
    ):
        raise AssistantNotFound("Assistant not found.")
    return assistant


@dataclass(frozen=True, slots=True)
class PublicAssistantConfiguration:
    id: str
    name: str
    welcome_message: str
    input_placeholder: str
    suggested_questions: tuple[str, ...]
    published_revision: int


class PublicAssistantConfigurationService:
    """Resolve the public identity and its immutable published presentation revision."""

    def __init__(
        self,
        assistant_repository: AssistantRepository,
        behaviour_repository: AssistantBehaviourRepository,
    ) -> None:
        self._assistant_repository = assistant_repository
        self._behaviour_repository = behaviour_repository

    def get(self, assistant_slug: str) -> PublicAssistantConfiguration:
        assistant = require_publicly_available(
            self._assistant_repository.get_by_slug(assistant_slug)
        )
        published = self._behaviour_repository.get_published(assistant.id)
        return PublicAssistantConfiguration(
            id=assistant.slug,
            name=assistant.name,
            welcome_message=published.welcome_message,
            input_placeholder=published.input_placeholder,
            suggested_questions=published.suggested_questions,
            published_revision=published.revision,
        )
