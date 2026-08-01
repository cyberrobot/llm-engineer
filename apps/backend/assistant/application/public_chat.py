import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID

from assistant.application.prompt_builder import Prompt, PromptBuilder
from assistant.application.public_chat_protection import TokenBudget
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
    estimated_input_tokens: int
    clock: Callable[[], float]

    def events(self) -> Iterator[PublicChatEvent]:
        """Produce one request-local typed stream with exactly one terminal event."""
        yield PublicChatEvent("start", {"assistant": self.assistant_slug})
        if self.prompt is None:
            yield PublicChatEvent("delta", {"text": self.insufficient_knowledge_response})
            yield PublicChatEvent("complete", {"finishReason": "stop"})
            public_chat_metrics.insufficient.inc()
            public_chat_metrics.completed.inc()
            public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
            self._log("insufficient_knowledge")
            return

        emitted_text = False
        estimated_output_tokens = 0
        provider_stream: Iterator[str] | None = None
        try:
            if self.clock() - self.started_at >= self.settings.request_timeout_seconds:
                raise TimeoutError
            generation_started_at = self.clock()
            provider_stream = self.provider.stream_response(
                system_prompt=self.prompt.system_prompt,
                user_prompt=self.prompt.user_prompt,
                max_output_tokens=self.settings.maximum_output_tokens,
                temperature=self.settings.temperature,
                timeout_seconds=max(
                    0.001,
                    min(
                        self.settings.first_token_timeout_seconds,
                        self.settings.request_timeout_seconds - (self.clock() - self.started_at),
                    ),
                ),
            )
            for delta in provider_stream:
                elapsed = self.clock() - self.started_at
                if not emitted_text and elapsed >= self.settings.first_token_timeout_seconds:
                    raise TimeoutError
                if elapsed >= self.settings.request_timeout_seconds:
                    raise TimeoutError
                if not delta:
                    continue
                if not emitted_text:
                    public_chat_metrics.time_to_first_token.observe(elapsed)
                emitted_text = True
                estimated_output_tokens += len(delta.encode("utf-8"))
                yield PublicChatEvent("delta", {"text": delta})
            if not emitted_text:
                raise RuntimeError("Generation completed without text.")
            public_chat_metrics.generation_duration.observe(self.clock() - generation_started_at)
        except GeneratorExit:
            close = getattr(provider_stream, "close", None)
            if close is not None:
                close()
            public_chat_metrics.cancelled.inc()
            self._log("cancelled")
            raise
        except TimeoutError:
            close = getattr(provider_stream, "close", None)
            if close is not None:
                close()
            public_chat_metrics.timeouts.inc()
            public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
            self._log("timed_out")
            yield PublicChatEvent(
                "error",
                {
                    "code": "request_timed_out",
                    "message": "The response could not be completed.",
                },
            )
            return
        except Exception:
            logger.error(
                "Public assistant chat generation failed",
                extra={"assistant_slug": self.assistant_slug},
            )
            public_chat_metrics.failures.inc()
            public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
            yield PublicChatEvent(
                "error",
                {
                    "code": "generation_failed",
                    "message": "The response could not be completed.",
                },
            )
            return

        yield PublicChatEvent("complete", {"finishReason": "stop"})
        public_chat_metrics.estimated_output_tokens.observe(estimated_output_tokens)
        public_chat_metrics.completed.inc()
        public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
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
                "estimated_input_tokens": self.estimated_input_tokens,
                "maximum_output_tokens": self.settings.maximum_output_tokens,
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
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._assistant_repository = assistant_repository
        self._retrieval_factory = retrieval_factory
        self._provider = provider
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._settings = settings or get_public_assistant_chat_settings()
        self._clock = clock

    def prepare(self, assistant_slug: str, request: PublicChatRequest) -> PreparedPublicChat:
        started_at = self._clock()
        public_chat_metrics.requests.inc()
        assistant = self._assistant_repository.get_by_slug(assistant_slug)
        if (
            assistant.status is not AssistantStatus.active
            or assistant.visibility is not AssistantVisibility.public
        ):
            # Public callers cannot distinguish unavailable assistants from absent ones.
            raise AssistantNotFound("Assistant not found.")

        retrieval_started_at = self._clock()
        chunks = self._retrieval_factory(assistant.id).retrieve(request.message)
        public_chat_metrics.retrieval_duration.observe(self._clock() - retrieval_started_at)
        if self._clock() - started_at >= self._settings.request_timeout_seconds:
            public_chat_metrics.timeouts.inc()
            raise PublicChatRequestTimedOut
        budget = TokenBudget(
            max_input_tokens=self._settings.maximum_input_tokens,
            max_context_tokens=self._settings.maximum_context_tokens,
            max_context_chunks=self._settings.maximum_context_chunks,
            model_context_tokens=self._settings.model_context_tokens,
            output_tokens=self._settings.maximum_output_tokens,
        )
        selected_contents = budget.select_context([chunk.content for chunk in chunks])
        selected_chunks: list[KnowledgeChunk] = []
        selected_index = 0
        for chunk in chunks:
            if selected_index >= len(selected_contents):
                break
            if chunk.content == selected_contents[selected_index]:
                selected_chunks.append(chunk)
                selected_index += 1
        chunks = selected_chunks
        prompt = (
            self._prompt_builder.build_public_chat(request.message, request.history, chunks)
            if chunks
            else None
        )
        try:
            estimated_input_tokens = (
                budget.validate_prompt(prompt.system_prompt, prompt.user_prompt) if prompt else 0
            )
        except ValueError as exc:
            public_chat_metrics.input_limit_rejections.inc()
            raise PublicChatInputLimitExceeded from exc
        public_chat_metrics.estimated_input_tokens.observe(estimated_input_tokens)
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
            estimated_input_tokens=estimated_input_tokens,
            clock=self._clock,
        )


class PublicChatInputLimitExceeded(ValueError):
    pass


class PublicChatRequestTimedOut(TimeoutError):
    pass
