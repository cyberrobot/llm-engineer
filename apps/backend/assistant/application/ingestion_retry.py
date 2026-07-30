from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random
from types import SimpleNamespace
from typing import Protocol, cast

import httpx
import psycopg
from tenacity import RetryCallState, wait_exponential

from assistant.application.knowledge_persistence_service import (
    IngestionPersistenceConflictError,
    IngestionPersistenceConsistencyError,
    IngestionPersistenceTransientError,
    InvalidKnowledgeInputError,
    KnowledgePersistenceError,
)
from assistant.application.ports.website_loader import (
    InvalidWebsiteUrl,
    WebsiteHTTPStatusError,
    WebsiteLoadError,
    WebsiteTimeoutError,
)
from assistant.domain.document_ingestion_job import IngestionStep
from core.config import IngestionRetrySettings
from infrastructure.ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)


class FailureCategory(str, Enum):
    network = "network"
    timeout = "timeout"
    rate_limit = "rate_limit"
    external_service = "external_service"
    database_transient = "database_transient"
    database_permanent = "database_permanent"
    validation = "validation"
    authentication = "authentication"
    authorisation = "authorisation"
    not_found = "not_found"
    unexpected = "unexpected"


@dataclass(frozen=True)
class IngestionFailure:
    category: FailureCategory
    failure_code: str
    failure_message: str
    retryable: bool
    provider_retry_delay_seconds: float | None = None


class FailureClassifier(Protocol):
    def classify(
        self, error: BaseException | IngestionFailure, step: IngestionStep
    ) -> IngestionFailure: ...


class IngestionFailureClassifier:
    """Translate typed boundary failures into safe, stable ingestion failures."""

    def classify(
        self, error: BaseException | IngestionFailure, step: IngestionStep
    ) -> IngestionFailure:
        if isinstance(error, IngestionFailure):
            return error

        for candidate in reversed(tuple(self._causes(error))):
            classified = self._classify_one(candidate, step)
            if classified is not None:
                return classified
        return IngestionFailure(
            FailureCategory.unexpected,
            "unexpected_ingestion_error",
            "Ingestion failed unexpectedly.",
            False,
        )

    def _classify_one(self, error: BaseException, step: IngestionStep) -> IngestionFailure | None:
        if isinstance(error, IngestionPersistenceTransientError):
            return self._failure(
                FailureCategory.database_transient,
                error.code,
                "Ingestion persistence is temporarily unavailable.",
                True,
            )
        if isinstance(error, IngestionPersistenceConflictError):
            return self._failure(
                FailureCategory.database_permanent,
                error.code,
                "Ingestion persistence conflicted with existing data.",
                False,
            )
        if isinstance(error, IngestionPersistenceConsistencyError):
            return self._failure(
                FailureCategory.database_permanent,
                error.code,
                "The committed ingestion result is inconsistent.",
                False,
            )
        if isinstance(error, InvalidKnowledgeInputError):
            return self._failure(
                FailureCategory.validation,
                error.code,
                "Ingestion persistence input is invalid.",
                False,
            )
        if isinstance(error, KnowledgePersistenceError) and step is IngestionStep.persist:
            return self._failure(
                FailureCategory.database_permanent,
                error.code,
                "Ingestion persistence failed.",
                False,
            )
        if isinstance(error, AIRateLimitError):
            return self._failure(
                FailureCategory.rate_limit,
                "ingestion_rate_limited",
                "The ingestion provider is temporarily rate limited.",
                True,
                self._retry_delay(error),
            )
        if isinstance(error, (AITimeoutError, WebsiteTimeoutError, httpx.TimeoutException)):
            return self._failure(
                FailureCategory.timeout,
                "ingestion_timeout",
                "The ingestion operation timed out.",
                True,
            )
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            if status == 429:
                return self._failure(
                    FailureCategory.rate_limit,
                    "ingestion_rate_limited",
                    "The ingestion provider is temporarily rate limited.",
                    True,
                    self._http_retry_after(error.response),
                )
            if status in {502, 503, 504}:
                return self._failure(
                    FailureCategory.external_service,
                    "ingestion_external_service_unavailable",
                    "The ingestion provider is temporarily unavailable.",
                    True,
                    self._http_retry_after(error.response),
                )
            if status in {401, 403}:
                category = (
                    FailureCategory.authentication
                    if status == 401
                    else FailureCategory.authorisation
                )
                return self._failure(
                    category,
                    f"ingestion_{category.value}_error",
                    f"The ingestion provider rejected {category.value}.",
                    False,
                )
            return self._failure(
                FailureCategory.validation,
                "ingestion_validation_error",
                "The ingestion provider rejected the request.",
                False,
            )
        if isinstance(error, WebsiteHTTPStatusError):
            status = error.status_code
            if status == 429 or status in {502, 503, 504}:
                category = (
                    FailureCategory.rate_limit
                    if status == 429
                    else FailureCategory.external_service
                )
                code = (
                    "ingestion_rate_limited"
                    if status == 429
                    else "ingestion_external_service_unavailable"
                )
                return self._failure(
                    category,
                    code,
                    "The ingestion source is temporarily unavailable.",
                    True,
                    error.retry_after_seconds,
                )
            if status in {401, 403}:
                category = (
                    FailureCategory.authentication
                    if status == 401
                    else FailureCategory.authorisation
                )
                return self._failure(
                    category,
                    f"ingestion_{category.value}_error",
                    "The ingestion source rejected access.",
                    False,
                )
            return self._failure(
                FailureCategory.validation,
                "ingestion_validation_error",
                "The ingestion source rejected retrieval.",
                False,
            )
        if isinstance(error, httpx.NetworkError):
            return self._failure(
                FailureCategory.network,
                "ingestion_network_error",
                "The ingestion provider could not be reached.",
                True,
            )
        if isinstance(error, AIUnavailableError):
            return self._failure(
                FailureCategory.external_service,
                "ingestion_external_service_unavailable",
                "The ingestion provider is temporarily unavailable.",
                True,
            )
        if isinstance(error, AIAuthenticationError):
            return self._failure(
                FailureCategory.authentication,
                "ingestion_authentication_error",
                "The ingestion provider rejected its credentials.",
                False,
            )
        if isinstance(error, (AIConfigurationError, AIProviderError)):
            return self._failure(
                FailureCategory.validation,
                "ingestion_validation_error",
                "The ingestion provider rejected the request.",
                False,
            )
        if isinstance(error, (psycopg.errors.UniqueViolation, psycopg.IntegrityError)):
            return self._failure(
                FailureCategory.database_permanent,
                "ingestion_database_permanent_error",
                "Ingestion data violated a database constraint.",
                False,
            )
        if isinstance(error, (psycopg.OperationalError, psycopg.errors.DeadlockDetected)):
            return self._failure(
                FailureCategory.database_transient,
                "ingestion_database_transient_error",
                "The ingestion database is temporarily unavailable.",
                True,
            )
        if isinstance(error, InvalidWebsiteUrl):
            return self._failure(
                FailureCategory.validation,
                "ingestion_validation_error",
                "The ingestion source is invalid.",
                False,
            )
        if isinstance(error, WebsiteLoadError):
            return self._failure(
                FailureCategory.external_service,
                "ingestion_external_service_unavailable",
                "The ingestion source could not be loaded.",
                False,
            )
        if isinstance(error, ValueError):
            return self._failure(
                FailureCategory.validation,
                "ingestion_validation_error",
                "Ingestion input is invalid.",
                False,
            )
        return None

    @staticmethod
    def _failure(
        category: FailureCategory,
        code: str,
        message: str,
        retryable: bool,
        delay: float | None = None,
    ) -> IngestionFailure:
        return IngestionFailure(category, code, message, retryable, delay)

    @staticmethod
    def _causes(error: BaseException):
        seen: set[int] = set()
        current: BaseException | None = error
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            yield current
            current = current.__cause__ or current.__context__

    @staticmethod
    def _retry_delay(error: BaseException) -> float | None:
        value = getattr(error, "retry_after_seconds", None)
        return float(value) if isinstance(value, (int, float)) and value >= 0 else None

    @staticmethod
    def _http_retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            delay = float(value)
        except ValueError:
            return None
        return delay if delay >= 0 else None


class IngestionRetryPolicy:
    def __init__(
        self,
        settings: IngestionRetrySettings,
        *,
        random_source: Random | None = None,
    ) -> None:
        self.settings = settings
        self._random = random_source or Random()
        self._wait = wait_exponential(
            multiplier=settings.initial_delay_seconds,
            exp_base=settings.backoff_multiplier,
            max=settings.maximum_delay_seconds,
        )

    def should_retry(self, failure: IngestionFailure, attempt_number: int) -> bool:
        return failure.retryable and attempt_number < self.settings.maximum_attempts

    def get_delay(self, retry_number: int, failure: IngestionFailure) -> float:
        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        state = cast(RetryCallState, SimpleNamespace(attempt_number=retry_number))
        local_delay = float(self._wait(state))
        if self.settings.jitter_enabled:
            local_delay = self._random.uniform(0, local_delay)
        provider_delay = failure.provider_retry_delay_seconds or 0
        return min(
            max(local_delay, provider_delay),
            self.settings.maximum_delay_seconds,
        )
