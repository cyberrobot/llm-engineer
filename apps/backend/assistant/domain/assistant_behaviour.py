from dataclasses import dataclass
from datetime import datetime
from unicodedata import category
from uuid import UUID

MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH = 12_000
MAX_WELCOME_MESSAGE_LENGTH = 1_000
MAX_INPUT_PLACEHOLDER_LENGTH = 160
MAX_SUGGESTED_QUESTIONS = 8
MAX_SUGGESTED_QUESTION_LENGTH = 240

DEFAULT_ASSISTANT_INSTRUCTIONS = (
    "Answer helpfully and concisely using only the knowledge supplied by the server."
)
DEFAULT_WELCOME_MESSAGE = "How can I help?"
DEFAULT_INPUT_PLACEHOLDER = "Ask a question"
DEFAULT_SUGGESTED_QUESTIONS: tuple[str, ...] = ()


def _has_unsafe_control(value: str, *, allow_multiline: bool) -> bool:
    allowed = {"\n", "\t"} if allow_multiline else set()
    return any(
        category(character) in {"Cc", "Cf", "Cs"} and character not in allowed
        for character in value
    )


@dataclass(frozen=True, slots=True)
class AssistantBehaviourRevision:
    assistant_id: UUID
    revision: int
    instructions: str
    welcome_message: str
    input_placeholder: str
    suggested_questions: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.assistant_id.int == 0:
            raise ValueError("Assistant ID must not be nil.")
        if self.revision < 1:
            raise ValueError("Behaviour revision must be positive.")
        if not self.instructions.strip():
            raise ValueError("Instructions must not be empty.")
        if len(self.instructions) > MAX_BEHAVIOUR_INSTRUCTIONS_LENGTH:
            raise ValueError("Instructions are too long.")
        if _has_unsafe_control(self.instructions, allow_multiline=True):
            raise ValueError("Instructions must not contain unsafe control characters.")
        if len(self.welcome_message) > MAX_WELCOME_MESSAGE_LENGTH:
            raise ValueError("Welcome message is too long.")
        if _has_unsafe_control(self.welcome_message, allow_multiline=True):
            raise ValueError("Welcome message must not contain unsafe control characters.")
        if not self.input_placeholder.strip():
            raise ValueError("Input placeholder must not be empty.")
        if len(self.input_placeholder) > MAX_INPUT_PLACEHOLDER_LENGTH:
            raise ValueError("Input placeholder is too long.")
        if _has_unsafe_control(self.input_placeholder, allow_multiline=False):
            raise ValueError("Input placeholder must be one safe line.")
        if len(self.suggested_questions) > MAX_SUGGESTED_QUESTIONS:
            raise ValueError("There are too many suggested questions.")
        for question in self.suggested_questions:
            if not question.strip():
                raise ValueError("Suggested questions must not be empty.")
            if len(question) > MAX_SUGGESTED_QUESTION_LENGTH:
                raise ValueError("A suggested question is too long.")
            if _has_unsafe_control(question, allow_multiline=False):
                raise ValueError("Suggested questions must be one safe line.")
        if self.created_at.tzinfo is None:
            raise ValueError("Behaviour timestamps must include a timezone.")

    def same_content_as(self, other: "AssistantBehaviourRevision") -> bool:
        return (
            self.instructions,
            self.welcome_message,
            self.input_placeholder,
            self.suggested_questions,
        ) == (
            other.instructions,
            other.welcome_message,
            other.input_placeholder,
            other.suggested_questions,
        )


@dataclass(frozen=True, slots=True)
class AssistantBehaviourState:
    assistant_id: UUID
    draft: AssistantBehaviourRevision
    published: AssistantBehaviourRevision | None
    published_at: datetime | None
    version: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Behaviour state version must be positive.")
        if self.draft.assistant_id != self.assistant_id:
            raise ValueError("Draft revision belongs to another Assistant.")
        if self.published is not None and self.published.assistant_id != self.assistant_id:
            raise ValueError("Published revision belongs to another Assistant.")
        if (self.published is None) != (self.published_at is None):
            raise ValueError("Published revision and publication timestamp must be set together.")
        if self.updated_at.tzinfo is None or (
            self.published_at is not None and self.published_at.tzinfo is None
        ):
            raise ValueError("Behaviour state timestamps must include a timezone.")

    @property
    def has_unpublished_changes(self) -> bool:
        return self.published is None or self.draft.revision != self.published.revision

    @property
    def concurrency_token(self) -> str:
        return str(self.version)


def default_behaviour_revision(
    assistant_id: UUID, *, created_at: datetime
) -> AssistantBehaviourRevision:
    return AssistantBehaviourRevision(
        assistant_id=assistant_id,
        revision=1,
        instructions=DEFAULT_ASSISTANT_INSTRUCTIONS,
        welcome_message=DEFAULT_WELCOME_MESSAGE,
        input_placeholder=DEFAULT_INPUT_PLACEHOLDER,
        suggested_questions=DEFAULT_SUGGESTED_QUESTIONS,
        created_at=created_at,
    )
