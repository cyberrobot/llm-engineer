import logging
from collections.abc import Iterator
from time import perf_counter
from typing import Any, Protocol, cast

import openai
from openai import OpenAI

from infrastructure.ai.exceptions import (
    AIAuthenticationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from infrastructure.ai.providers.base import AIProvider

logger = logging.getLogger(__name__)


class _Response(Protocol):
    output_text: str


class _ResponsesAPI(Protocol):
    def create(
        self, *, model: str, instructions: str, input: str, **options: Any
    ) -> _Response | Any: ...


class _Embedding(Protocol):
    embedding: list[float]


class _EmbeddingResponse(Protocol):
    data: list[_Embedding]


class _EmbeddingsAPI(Protocol):
    def create(self, *, model: str, input: str | list[str]) -> _EmbeddingResponse: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesAPI
    embeddings: _EmbeddingsAPI


class OpenAIProvider(AIProvider):
    """OpenAI adapter that contains all SDK-specific behavior."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int = 2,
        embedding_model: str = "text-embedding-3-small",
        client: _OpenAIClient | None = None,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._owns_client = client is None
        self._client = cast(
            _OpenAIClient,
            client or OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries),
        )

    def close(self) -> None:
        """Close the provider-owned SDK client and its HTTP connection pool."""
        if self._owns_client:
            close = getattr(self._client, "close", None)
            if close is not None:
                close()

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        started_at = perf_counter()
        try:
            response = self._client.responses.create(
                model=self._model,
                instructions=system_prompt,
                input=user_prompt,
            )
            output = response.output_text.strip()
            if not output:
                raise AIProviderError("The AI provider returned an empty response.")
        except AIProviderError:
            self._log_result(started_at, success=False)
            raise
        except openai.AuthenticationError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.PermissionDeniedError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.RateLimitError as exc:
            self._log_result(started_at, success=False)
            raise AIRateLimitError(retry_after_seconds=self._retry_after(exc)) from exc
        except openai.APITimeoutError as exc:
            self._log_result(started_at, success=False)
            raise AITimeoutError from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:
            self._log_result(started_at, success=False)
            raise AIUnavailableError from exc
        except openai.APIError as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc
        except Exception as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc

        self._log_result(started_at, success=True)
        return output

    def generate_embedding(self, *, text: str) -> list[float]:
        """Generate one embedding and translate SDK failures at the adapter boundary."""
        embeddings = self._generate_embeddings(text)
        return embeddings[0]

    def stream_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
    ) -> Iterator[str]:
        """Yield Responses API text deltas and close the SDK stream on cancellation."""
        started_at = perf_counter()
        stream: Any = None
        try:
            request_options: dict[str, Any] = {}
            if timeout_seconds is not None:
                request_options["timeout"] = timeout_seconds
            stream = self._client.responses.create(
                model=self._model,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                stream=True,
                **request_options,
            )
            for event in stream:
                event_type = getattr(event, "type", None)
                if event_type == "response.completed":
                    self._log_usage(getattr(event, "response", None))
                    continue
                if event_type != "response.output_text.delta":
                    continue
                delta = getattr(event, "delta", "")
                if delta:
                    yield str(delta)
        except GeneratorExit:
            raise
        except AIProviderError:
            self._log_result(started_at, success=False)
            raise
        except openai.AuthenticationError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.PermissionDeniedError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.RateLimitError as exc:
            self._log_result(started_at, success=False)
            raise AIRateLimitError(retry_after_seconds=self._retry_after(exc)) from exc
        except openai.APITimeoutError as exc:
            self._log_result(started_at, success=False)
            raise AITimeoutError from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:
            self._log_result(started_at, success=False)
            raise AIUnavailableError from exc
        except openai.APIError as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc
        except Exception as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc
        else:
            self._log_result(started_at, success=True)
        finally:
            if stream is not None:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        """Generate one ordered provider vector per supplied text in a single request."""
        if not texts:
            return []
        return self._generate_embeddings(texts)

    def _generate_embeddings(self, inputs: str | list[str]) -> list[list[float]]:
        started_at = perf_counter()
        try:
            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=inputs,
            )
            if not response.data or any(not item.embedding for item in response.data):
                raise AIProviderError("The AI provider returned an empty embedding.")
            embeddings = [item.embedding for item in response.data]
        except AIProviderError:
            self._log_result(started_at, success=False)
            raise
        except openai.AuthenticationError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.PermissionDeniedError as exc:
            self._log_result(started_at, success=False)
            raise AIAuthenticationError from exc
        except openai.RateLimitError as exc:
            self._log_result(started_at, success=False)
            raise AIRateLimitError(retry_after_seconds=self._retry_after(exc)) from exc
        except openai.APITimeoutError as exc:
            self._log_result(started_at, success=False)
            raise AITimeoutError from exc
        except (openai.APIConnectionError, openai.InternalServerError) as exc:
            self._log_result(started_at, success=False)
            raise AIUnavailableError from exc
        except openai.APIError as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc
        except Exception as exc:
            self._log_result(started_at, success=False)
            raise AIProviderError from exc

        self._log_result(started_at, success=True)
        return embeddings

    def _log_result(self, started_at: float, *, success: bool) -> None:
        log = logger.info if success else logger.warning
        log(
            "AI provider request completed",
            extra={
                "provider": self.name,
                "model": self.model,
                "duration_ms": round((perf_counter() - started_at) * 1_000, 2),
                "success": success,
            },
        )

    def _log_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        logger.info(
            "AI provider token usage recorded",
            extra={
                "provider": self.name,
                "model": self.model,
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        )

    @staticmethod
    def _retry_after(error: openai.RateLimitError) -> float | None:
        value = error.response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            delay = float(value)
        except ValueError:
            return None
        return delay if delay >= 0 else None
