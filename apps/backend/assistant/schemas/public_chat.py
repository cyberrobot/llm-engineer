from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.config import get_public_assistant_chat_settings

MAX_PUBLIC_CHAT_MESSAGE_LENGTH = 4_000
MAX_PUBLIC_CHAT_REQUEST_BYTES = 32_768
MAX_HISTORY_MESSAGE_LENGTH = 4_000
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_TOTAL_LENGTH = 12_000
MAX_HISTORY_ESTIMATED_TOKENS = 12_000


class PublicChatHistoryMessage(BaseModel):
    """One untrusted, completed conversation-history message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class PublicChatRequest(BaseModel):
    """The public widget's current message and bounded completed prior turns."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    history: list[PublicChatHistoryMessage] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_turns(self) -> "PublicChatRequest":
        settings = get_public_assistant_chat_settings()
        if len(self.message) > settings.maximum_message_characters:
            raise ValueError("Message exceeds the character limit.")
        if len(self.history) > settings.maximum_history_messages:
            raise ValueError("History contains too many messages.")
        if len(self.history) % 2:
            raise ValueError("History must contain completed user and assistant turns.")
        for index, item in enumerate(self.history):
            expected = "user" if index % 2 == 0 else "assistant"
            if item.role != expected:
                raise ValueError("History must alternate user and assistant messages.")
        if any(
            len(item.content) > settings.maximum_history_message_characters for item in self.history
        ):
            raise ValueError("History exceeds the per-message character limit.")
        total_characters = sum(len(item.content) for item in self.history)
        if total_characters > settings.maximum_history_characters:
            raise ValueError("History exceeds the total character limit.")
        estimated_tokens = sum(len(item.content.encode("utf-8")) + 4 for item in self.history)
        if estimated_tokens > settings.maximum_history_tokens:
            raise ValueError("History exceeds the estimated token limit.")
        return self


class PublicChatErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class PublicChatErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: PublicChatErrorDetail


class PublicChatStartEvent(BaseModel):
    assistant: str


class PublicChatDeltaEvent(BaseModel):
    text: str


class PublicChatCompleteEvent(BaseModel):
    finishReason: Literal["stop"] = "stop"


class PublicChatErrorEvent(BaseModel):
    code: Literal["generation_failed", "request_timed_out"] = "generation_failed"
    message: str = "The response could not be completed."
