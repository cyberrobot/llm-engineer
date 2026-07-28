import logging
from time import perf_counter
from typing import Protocol, cast

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
    def create(self, *, model: str, instructions: str, input: str) -> _Response: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesAPI


class OpenAIProvider(AIProvider):
    """OpenAI adapter that contains all SDK-specific behavior."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float,
        client: _OpenAIClient | None = None,
    ) -> None:
        self._model = model
        self._client = cast(
            _OpenAIClient,
            client or OpenAI(api_key=api_key, timeout=timeout),
        )

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
            raise AIRateLimitError from exc
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
