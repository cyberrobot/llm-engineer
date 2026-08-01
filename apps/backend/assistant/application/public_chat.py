import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID

from assistant.application.prompt_builder import Prompt, PromptBuilder
from assistant.domain import KnowledgeChunk
from assistant.domain.assistant import AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import AssistantNotFound, AssistantRepository
from assistant.schemas.public_chat import PublicChatRequest
from core.config import PublicAssistantChatSettings, get_public_assistant_chat_settings
from core.correlation import request_id_context
from core.metrics import public_chat_metrics
from infrastructure.ai.providers import AIProvider

logger = logging.getLogger(__name__)

INSUFFICIENT_KNOWLEDGE_RESPONSE = (
    "I don’t have enough information in the Redmoor knowledge base to answer that."
)
GENERIC_INSUFFICIENT_KNOWLEDGE_RESPONSE = (
    "I don’t have enough information in this assistant’s knowledge base to answer that."
)


class ScopedRetrieval(Protocol):
    def retrieve(self, query: str) -> list[KnowledgeChunk]: ...


@dataclass(frozen=True, slots=True)
class PublicChatEvent:
    type: Literal["start", "delta", "complete", "error"]
    payload: dict[str, str]


@dataclass(frozen=True, slots=True)
class PreparedPublicChat:
    assistant_slug: str
    prompt: Prompt | None
    chunks: tuple[KnowledgeChunk, ...]
    provider: AIProvider
    settings: PublicAssistantChatSettings
    started_at: float
    request_id: str | None
    insufficient_knowledge_response: str

    def events(self) -> Iterator[PublicChatEvent]:
        """Produce one request-local typed stream with exactly one terminal event."""
        yield PublicChatEvent("start", {"assistant": self.assistant_slug})
        if self.prompt is None:
            yield PublicChatEvent("delta", {"text": self.insufficient_knowledge_response})
            yield PublicChatEvent("complete", {"finishReason": "stop"})
            public_chat_metrics.insufficient.inc()
            public_chat_metrics.completed.inc()
            public_chat_metrics.total_duration.observe(perf_counter() - self.started_at)
            self._log("insufficient_knowledge")
            return

        emitted_text = False
        provider_stream: Iterator[str] | None = None
        try:
            generation_started_at = perf_counter()
            provider_stream = self.provider.stream_response(
                system_prompt=self.prompt.system_prompt,
                user_prompt=self.prompt.user_prompt,
                max_output_tokens=self.settings.maximum_output_tokens,
                temperature=self.settings.temperature,
            )
            for delta in provider_stream:
                if not delta:
                    continue
                emitted_text = True
                yield PublicChatEvent("delta", {"text": delta})
            if not emitted_text:
                raise RuntimeError("Generation completed without text.")
            public_chat_metrics.generation_duration.observe(perf_counter() - generation_started_at)
        except GeneratorExit:
            close = getattr(provider_stream, "close", None)
            if close is not None:
                close()
            public_chat_metrics.cancelled.inc()
            self._log("cancelled")
            raise
        except Exception:
            logger.error(
                "Public assistant chat generation failed",
                extra={"assistant_slug": self.assistant_slug},
            )
            public_chat_metrics.failures.inc()
            public_chat_metrics.total_duration.observe(perf_counter() - self.started_at)
            yield PublicChatEvent(
                "error",
                {
                    "code": "generation_failed",
                    "message": "The response could not be completed.",
                },
            )
            return

        yield PublicChatEvent("complete", {"finishReason": "stop"})
        public_chat_metrics.completed.inc()
        public_chat_metrics.total_duration.observe(perf_counter() - self.started_at)
        self._log("completed")

    def _log(self, outcome: str) -> None:
        logger.info(
            "Public assistant chat finished",
            extra={
                "request_id": self.request_id,
                "assistant_slug": self.assistant_slug,
                "model": self.provider.model,
                "retrieved_chunk_ids": [chunk.id for chunk in self.chunks],
                "accepted_context_count": len(self.chunks),
                "generation_outcome": outcome,
            },
        )


class PublicAssistantChatService:
    """Resolve, validate, retrieve, and prepare public assistant chat streams."""

    def __init__(
        self,
        assistant_repository: AssistantRepository,
        retrieval_factory: Callable[[UUID], ScopedRetrieval],
        provider: AIProvider,
        prompt_builder: PromptBuilder | None = None,
        settings: PublicAssistantChatSettings | None = None,
    ) -> None:
        self._assistant_repository = assistant_repository
        self._retrieval_factory = retrieval_factory
        self._provider = provider
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._settings = settings or get_public_assistant_chat_settings()

    def prepare(self, assistant_slug: str, request: PublicChatRequest) -> PreparedPublicChat:
        started_at = perf_counter()
        public_chat_metrics.requests.inc()
        assistant = self._assistant_repository.get_by_slug(assistant_slug)
        if (
            assistant.status is not AssistantStatus.active
            or assistant.visibility is not AssistantVisibility.public
        ):
            # Public callers cannot distinguish unavailable assistants from absent ones.
            raise AssistantNotFound("Assistant not found.")

        retrieval_started_at = perf_counter()
        chunks = self._retrieval_factory(assistant.id).retrieve(request.message)
        public_chat_metrics.retrieval_duration.observe(perf_counter() - retrieval_started_at)
        prompt = (
            self._prompt_builder.build_public_chat(request.message, request.history, chunks)
            if chunks
            else None
        )
        logger.info(
            "Public assistant chat prepared",
            extra={
                "request_id": request_id_context.get(),
                "assistant_id": str(assistant.id),
                "assistant_slug": assistant.slug,
                "history_message_count": len(request.history),
                "input_length": len(request.message),
                "retrieved_candidate_count": len(chunks),
                "insufficient_knowledge": not chunks,
                "model": self._provider.model,
            },
        )
        return PreparedPublicChat(
            assistant_slug=assistant.slug,
            prompt=prompt,
            chunks=tuple(chunks),
            provider=self._provider,
            settings=self._settings,
            started_at=started_at,
            request_id=request_id_context.get(),
            insufficient_knowledge_response=(
                INSUFFICIENT_KNOWLEDGE_RESPONSE
                if assistant.slug == "redmoor"
                else GENERIC_INSUFFICIENT_KNOWLEDGE_RESPONSE
            ),
        )
