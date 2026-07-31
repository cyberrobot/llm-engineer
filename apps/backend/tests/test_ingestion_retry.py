from random import Random

import httpx
import psycopg
import pytest

from assistant.application.ingestion_retry import (
    FailureCategory,
    IngestionFailure,
    IngestionFailureClassifier,
    IngestionRetryPolicy,
)
from assistant.application.knowledge_persistence_service import (
    IngestionPersistenceConflictError,
    IngestionPersistenceTransientError,
    InvalidKnowledgeInputError,
)
from assistant.application.ports.website_loader import (
    InvalidWebsiteUrl,
    WebsiteHTTPStatusError,
    WebsiteLoadError,
    WebsiteTimeoutError,
)
from assistant.domain.document_ingestion_job import IngestionStep
from core.config import IngestionRetrySettings, get_ingestion_retry_settings
from infrastructure.ai.exceptions import (
    AIAuthenticationError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)


@pytest.mark.parametrize(
    ("error", "category", "code"),
    [
        (
            httpx.ConnectError("private upstream detail"),
            FailureCategory.network,
            "ingestion_network_error",
        ),
        (
            WebsiteTimeoutError("private upstream detail"),
            FailureCategory.timeout,
            "ingestion_timeout",
        ),
        (AITimeoutError("private upstream detail"), FailureCategory.timeout, "ingestion_timeout"),
        (
            AIRateLimitError("private upstream detail"),
            FailureCategory.rate_limit,
            "ingestion_rate_limited",
        ),
        (
            AIUnavailableError("private upstream detail"),
            FailureCategory.external_service,
            "ingestion_external_service_unavailable",
        ),
        (
            psycopg.OperationalError("private database detail"),
            FailureCategory.database_transient,
            "ingestion_database_transient_error",
        ),
        (
            IngestionPersistenceTransientError("private database detail"),
            FailureCategory.database_transient,
            "ingestion_persistence_transient_error",
        ),
    ],
)
def test_classifier_maps_typed_transient_failures_without_leaking_messages(error, category, code):
    failure = IngestionFailureClassifier().classify(error, IngestionStep.embed)

    assert failure.retryable
    assert failure.category is category
    assert failure.failure_code == code
    assert "private" not in failure.failure_message


@pytest.mark.parametrize(
    ("error", "category", "code"),
    [
        (
            InvalidWebsiteUrl("private input"),
            FailureCategory.validation,
            "ingestion_validation_error",
        ),
        (
            AIAuthenticationError("private credential"),
            FailureCategory.authentication,
            "ingestion_authentication_error",
        ),
        (
            psycopg.errors.UniqueViolation("private constraint"),
            FailureCategory.database_permanent,
            "ingestion_database_permanent_error",
        ),
        (
            ValueError("private validation"),
            FailureCategory.validation,
            "ingestion_validation_error",
        ),
        (
            InvalidKnowledgeInputError("private validation"),
            FailureCategory.validation,
            "invalid_ingestion_persistence_input",
        ),
        (
            IngestionPersistenceConflictError("private constraint"),
            FailureCategory.database_permanent,
            "ingestion_persistence_conflict",
        ),
        (RuntimeError("private bug"), FailureCategory.unexpected, "unexpected_ingestion_error"),
    ],
)
def test_classifier_maps_permanent_and_unknown_failures_as_non_retryable(error, category, code):
    failure = IngestionFailureClassifier().classify(error, IngestionStep.persist)

    assert not failure.retryable
    assert failure.category is category
    assert failure.failure_code == code
    assert "private" not in failure.failure_message


def test_classifier_uses_supported_http_statuses_and_preserves_classified_failure():
    request = httpx.Request("POST", "https://provider.invalid/embed")
    response = httpx.Response(429, request=request, headers={"Retry-After": "7"})
    failure = IngestionFailureClassifier().classify(
        httpx.HTTPStatusError("private body", request=request, response=response),
        IngestionStep.embed,
    )

    assert failure.retryable
    assert failure.category is FailureCategory.rate_limit
    assert failure.provider_retry_delay_seconds == 7
    assert IngestionFailureClassifier().classify(failure, IngestionStep.parse) is failure


def test_classifier_uses_root_typed_cause_instead_of_retrying_permanent_wrapper():
    try:
        try:
            raise InvalidWebsiteUrl("private invalid URL")
        except InvalidWebsiteUrl as cause:
            raise WebsiteLoadError("safe loader wrapper") from cause
    except WebsiteLoadError as error:
        failure = IngestionFailureClassifier().classify(error, IngestionStep.parse)

    assert not failure.retryable
    assert failure.category is FailureCategory.validation


@pytest.mark.parametrize(("status", "retryable"), [(503, True), (404, False)])
def test_classifier_uses_typed_website_status_without_message_matching(status, retryable):
    failure = IngestionFailureClassifier().classify(
        WebsiteHTTPStatusError(status, retry_after_seconds=3), IngestionStep.parse
    )

    assert failure.retryable is retryable
    assert failure.provider_retry_delay_seconds == (3 if retryable else None)


def retry_settings(
    *,
    maximum_attempts: int = 4,
    initial_delay_seconds: float = 1,
    backoff_multiplier: float = 2,
    maximum_delay_seconds: float = 5,
    jitter_enabled: bool = False,
) -> IngestionRetrySettings:
    return IngestionRetrySettings(
        maximum_attempts,
        initial_delay_seconds,
        backoff_multiplier,
        maximum_delay_seconds,
        jitter_enabled,
    )


def test_retry_policy_enforces_attempt_semantics_and_exponential_backoff():
    policy = IngestionRetryPolicy(retry_settings())
    retryable = IngestionFailure(
        FailureCategory.timeout, "ingestion_timeout", "The request timed out.", True
    )
    permanent = IngestionFailure(
        FailureCategory.validation, "ingestion_validation_error", "Input is invalid.", False
    )

    assert policy.should_retry(retryable, attempt_number=1)
    assert policy.should_retry(retryable, attempt_number=3)
    assert not policy.should_retry(retryable, attempt_number=4)
    assert not policy.should_retry(permanent, attempt_number=1)
    assert [policy.get_delay(retry_number=n, failure=retryable) for n in range(1, 5)] == [
        1,
        2,
        4,
        5,
    ]


def test_retry_policy_respects_provider_minimum_cap_and_controllable_jitter():
    failure = IngestionFailure(
        FailureCategory.rate_limit,
        "ingestion_rate_limited",
        "The provider is rate limited.",
        True,
        provider_retry_delay_seconds=4,
    )
    capped = IngestionRetryPolicy(retry_settings(maximum_delay_seconds=5))
    jittered = IngestionRetryPolicy(retry_settings(jitter_enabled=True), random_source=Random(1234))

    assert capped.get_delay(retry_number=1, failure=failure) == 4
    assert capped.get_delay(retry_number=4, failure=failure) == 5
    assert jittered.get_delay(retry_number=2, failure=failure) == pytest.approx(4.0)


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"INGESTION_RETRY_MAX_ATTEMPTS": "0"}, "at least 1"),
        ({"INGESTION_RETRY_INITIAL_DELAY_SECONDS": "-1"}, "not be negative"),
        ({"INGESTION_RETRY_BACKOFF_MULTIPLIER": "0.5"}, "at least 1"),
        (
            {
                "INGESTION_RETRY_MAX_DELAY_SECONDS": "0.5",
                "INGESTION_RETRY_INITIAL_DELAY_SECONDS": "1",
            },
            "not be smaller",
        ),
        ({"INGESTION_RETRY_JITTER_ENABLED": "sometimes"}, "must be true or false"),
    ],
)
def test_invalid_retry_configuration_is_rejected(monkeypatch, environment, message):
    for name in (
        "INGESTION_RETRY_MAX_ATTEMPTS",
        "INGESTION_RETRY_INITIAL_DELAY_SECONDS",
        "INGESTION_RETRY_BACKOFF_MULTIPLIER",
        "INGESTION_RETRY_MAX_DELAY_SECONDS",
        "INGESTION_RETRY_JITTER_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        get_ingestion_retry_settings()


def test_retry_configuration_defaults_define_total_attempts(monkeypatch):
    for name in (
        "INGESTION_RETRY_MAX_ATTEMPTS",
        "INGESTION_RETRY_INITIAL_DELAY_SECONDS",
        "INGESTION_RETRY_BACKOFF_MULTIPLIER",
        "INGESTION_RETRY_MAX_DELAY_SECONDS",
        "INGESTION_RETRY_JITTER_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    assert get_ingestion_retry_settings() == IngestionRetrySettings(3, 1, 2, 30, True)
