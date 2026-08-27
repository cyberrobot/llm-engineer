import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID

from assistant.application.prompt_builder import Prompt, PromptBuilder
from assistant.application.public_assistant import require_publicly_available
from assistant.application.public_chat_protection import TokenBudget
from assistant.domain import KnowledgeChunk
from assistant.domain.assistant import Assistant
from assistant.domain.assistant_behaviour import DEFAULT_ASSISTANT_INSTRUCTIONS
from assistant.domain.assistant_behaviour_repository import AssistantBehaviourRepository
from assistant.schemas.public_chat import PublicChatRequest
from core.config import PublicAssistantChatSettings, get_public_assistant_chat_settings
from core.correlation import request_id_context
from core.metrics import assistant_preview_metrics, public_chat_metrics
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


class PublicAssistantLookup(Protocol):
    def get_by_slug(self, slug: str) -> Assistant: ...
    def get_by_id(self, assistant_id: UUID) -> Assistant: ...


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
    mode: Literal["public", "preview"] = "public"

    def events(self) -> Iterator[PublicChatEvent]:
        """Produce one request-local typed stream with exactly one terminal event."""
        yield PublicChatEvent("start", {"assistant": self.assistant_slug})
        if self.prompt is None:
            yield PublicChatEvent("delta", {"text": self.insufficient_knowledge_response})
            yield PublicChatEvent("complete", {"finishReason": "stop"})
            if self.mode == "public":
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
                    if self.mode == "public":
                        public_chat_metrics.time_to_first_token.observe(elapsed)
                emitted_text = True
                estimated_output_tokens += len(delta.encode("utf-8"))
                yield PublicChatEvent("delta", {"text": delta})
            if not emitted_text:
                raise RuntimeError("Generation completed without text.")
            if self.mode == "public":
                public_chat_metrics.generation_duration.observe(
                    self.clock() - generation_started_at
                )
        except GeneratorExit:
            close = getattr(provider_stream, "close", None)
            if close is not None:
                close()
            if self.mode == "public":
                public_chat_metrics.cancelled.inc()
            self._log("cancelled")
            raise
        except TimeoutError:
            close = getattr(provider_stream, "close", None)
            if close is not None:
                close()
            if self.mode == "public":
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
                "Public assistant chat generation failed"
                if self.mode == "public"
                else "assistant_preview_generation_failed",
                extra={"assistant_slug": self.assistant_slug},
            )
            if self.mode == "public":
                public_chat_metrics.failures.inc()
                public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
            self._log("failed")
            yield PublicChatEvent(
                "error",
                {
                    "code": "generation_failed",
                    "message": "The response could not be completed.",
                },
            )
            return

        yield PublicChatEvent("complete", {"finishReason": "stop"})
        if self.mode == "public":
            public_chat_metrics.estimated_output_tokens.observe(estimated_output_tokens)
            public_chat_metrics.completed.inc()
            public_chat_metrics.total_duration.observe(self.clock() - self.started_at)
        self._log("completed")

    def _log(self, outcome: str) -> None:
        if self.mode == "preview":
            operation_outcome = (
                "completed" if outcome in {"completed", "insufficient_knowledge"} else "failed"
            )
            try:
                assistant_preview_metrics.operations.labels(outcome=operation_outcome).inc()
            except Exception:
                pass
            logger.info(
                f"assistant_preview_{operation_outcome}",
                extra={
                    "request_id": self.request_id,
                    "assistant_slug": self.assistant_slug,
                    "generation_outcome": outcome,
                    "accepted_context_count": len(self.chunks),
                },
            )
            return
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
        assistant_repository: PublicAssistantLookup,
        retrieval_factory: Callable[[UUID], ScopedRetrieval],
        provider: AIProvider,
        prompt_builder: PromptBuilder | None = None,
        settings: PublicAssistantChatSettings | None = None,
        clock: Callable[[], float] = perf_counter,
        behaviour_repository: AssistantBehaviourRepository | None = None,
    ) -> None:
        self._assistant_repository = assistant_repository
        self._retrieval_factory = retrieval_factory
        self._provider = provider
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._settings = settings or get_public_assistant_chat_settings()
        self._clock = clock
        self._behaviour_repository = behaviour_repository

    def prepare(self, assistant_slug: str, request: PublicChatRequest) -> PreparedPublicChat:
        started_at = self._clock()
        public_chat_metrics.requests.inc()
        assistant = require_publicly_available(
            self._assistant_repository.get_by_slug(assistant_slug)
        )
        return self.prepare_resolved(
            assistant,
            request,
            started_at=started_at,
            enforce_public_availability=False,
            instructions=(
                self._behaviour_repository.get_published(assistant.id).instructions
                if self._behaviour_repository is not None
                else DEFAULT_ASSISTANT_INSTRUCTIONS
            ),
        )

    def prepare_resolved(
        self,
        assistant: Assistant,
        request: PublicChatRequest,
        *,
        started_at: float | None = None,
        enforce_public_availability: bool,
        instructions: str,
        mode: Literal["public", "preview"] = "public",
    ) -> PreparedPublicChat:
        """Prepare one grounded request for public or authenticated preview execution."""
        started_at = self._clock() if started_at is None else started_at
        if enforce_public_availability:
            require_publicly_available(assistant)

        retrieval_started_at = self._clock()
        chunks = self._retrieval_factory(assistant.id).retrieve(request.message)
        if mode == "public":
            public_chat_metrics.retrieval_duration.observe(self._clock() - retrieval_started_at)
        if self._clock() - started_at >= self._settings.request_timeout_seconds:
            if mode == "public":
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
            self._prompt_builder.build_public_chat(
                request.message, request.history, chunks, instructions
            )
            if chunks
            else None
        )
        try:
            estimated_input_tokens = (
                budget.validate_prompt(prompt.system_prompt, prompt.user_prompt) if prompt else 0
            )
        except ValueError as exc:
            if mode == "public":
                public_chat_metrics.input_limit_rejections.inc()
            raise PublicChatInputLimitExceeded from exc
        if mode == "public":
            public_chat_metrics.estimated_input_tokens.observe(estimated_input_tokens)
        logger.info(
            "Public assistant chat prepared" if mode == "public" else "assistant_preview_prepared",
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
            mode=mode,
        )


class PublicChatInputLimitExceeded(ValueError):
    pass


class PublicChatRequestTimedOut(TimeoutError):
    pass


class AssistantPreviewChatService:
    """Prepare admin preview through the same retrieval, prompt, and provider pipeline."""

    def __init__(
        self,
        assistant_repository: PublicAssistantLookup,
        behaviour_repository: AssistantBehaviourRepository,
        retrieval_factory: Callable[[UUID], ScopedRetrieval],
        provider: AIProvider,
        prompt_builder: PromptBuilder | None = None,
        settings: PublicAssistantChatSettings | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._assistant_repository = assistant_repository
        self._behaviour_repository = behaviour_repository
        self._preparation = PublicAssistantChatService(
            assistant_repository,
            retrieval_factory,
            provider,
            prompt_builder,
            settings,
            clock,
            behaviour_repository,
        )

    def prepare(self, assistant_id: UUID, request: PublicChatRequest) -> PreparedPublicChat:
        assistant = self._assistant_repository.get_by_id(assistant_id)
        # Resolve exactly once so the request remains internally consistent during later saves.
        draft = self._behaviour_repository.get_state(assistant_id).draft
        logger.info(
            "assistant_preview_started",
            extra={"assistant_id": str(assistant_id), "draft_revision": draft.revision},
        )
        try:
            return self._preparation.prepare_resolved(
                assistant,
                request,
                enforce_public_availability=False,
                instructions=draft.instructions,
                mode="preview",
            )
        except Exception:
            try:
                assistant_preview_metrics.operations.labels(outcome="failed").inc()
            except Exception:
                pass
            logger.error(
                "assistant_preview_failed",
                extra={"assistant_id": str(assistant_id), "draft_revision": draft.revision},
            )
            raise
