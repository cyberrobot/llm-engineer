from pydantic import BaseModel, ConfigDict, Field

from assistant.schemas.common import SourceReference

MAX_CHAT_MESSAGE_LENGTH = 4_000


class ChatRequest(BaseModel):
    """A message submitted to the Assistant."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGE_LENGTH,
        description="The user's message, without surrounding whitespace",
        examples=["How can the discovery process help my team?"],
    )


class ChatResponse(BaseModel):
    """A future Assistant response and its supporting sources."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        description="The Assistant's response",
        examples=["A discovery workshop can clarify your team's priorities."],
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Sources supporting the response",
    )
