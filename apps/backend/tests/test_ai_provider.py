import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import openai
import pytest

from core.config import AISettings, get_ai_settings
from infrastructure.ai.client import create_ai_provider
from infrastructure.ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
    AIUnavailableError,
)
from infrastructure.ai.providers.openai import OpenAIProvider


def make_provider(response_or_error) -> tuple[OpenAIProvider, Mock]:
    client = Mock()
    if isinstance(response_or_error, Exception):
        client.responses.create.side_effect = response_or_error
    else:
        client.responses.create.return_value = SimpleNamespace(output_text=response_or_error)
    return (
        OpenAIProvider(
            api_key="test-key",
            model="test-model",
            timeout=5,
            client=client,
        ),
        client,
    )


def status_error(error_type, status_code: int) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_type("provider error", response=response, body=None)


def test_openai_provider_returns_text_without_leaking_sdk_response(caplog):
    provider, client = make_provider("  Generated answer  ")

    with caplog.at_level(logging.INFO):
        result = provider.generate_response(
            system_prompt="System instructions",
            user_prompt="Sensitive user message",
        )

    assert result == "Generated answer"
    client.responses.create.assert_called_once_with(
        model="test-model",
        instructions="System instructions",
        input="Sensitive user message",
    )
    record = caplog.records[-1]
    assert record.provider == "openai"
    assert record.model == "test-model"
    assert record.success is True
    assert "Sensitive user message" not in record.getMessage()


@pytest.mark.parametrize(
    ("sdk_error", "expected_error"),
    [
        (status_error(openai.AuthenticationError, 401), AIAuthenticationError),
        (status_error(openai.RateLimitError, 429), AIRateLimitError),
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            AITimeoutError,
        ),
        (
            openai.APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            AIUnavailableError,
        ),
        (RuntimeError("unexpected"), AIProviderError),
    ],
)
def test_openai_provider_translates_external_failures(sdk_error, expected_error):
    provider, _ = make_provider(sdk_error)

    with pytest.raises(expected_error) as raised:
        provider.generate_response(system_prompt="system", user_prompt="user")

    assert "unexpected" not in str(raised.value)
    assert "provider error" not in str(raised.value)


def test_openai_provider_rejects_empty_output():
    provider, _ = make_provider("  ")

    with pytest.raises(AIProviderError, match="empty response"):
        provider.generate_response(system_prompt="system", user_prompt="user")


def test_openai_provider_generates_embedding_through_provider_boundary():
    provider, client = make_provider("answer")
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
    )

    result = provider.generate_embedding(text="Knowledge query")

    assert result == [0.1, 0.2, 0.3]
    client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input="Knowledge query",
    )


def test_openai_provider_generates_batch_embeddings_in_provider_order():
    provider, client = make_provider("answer")
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(embedding=[1.0, 0.0]),
            SimpleNamespace(embedding=[0.0, 1.0]),
        ]
    )

    result = provider.generate_embeddings(texts=["First", "Second"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input=["First", "Second"],
    )


def test_openai_provider_rejects_empty_batch_without_calling_sdk():
    provider, client = make_provider("answer")

    assert provider.generate_embeddings(texts=[]) == []

    client.embeddings.create.assert_not_called()


def test_openai_provider_rejects_empty_embedding():
    provider, client = make_provider("answer")
    client.embeddings.create.return_value = SimpleNamespace(data=[])

    with pytest.raises(AIProviderError, match="empty embedding"):
        provider.generate_embedding(text="Knowledge query")


def test_provider_factory_selects_openai_from_settings():
    settings = AISettings(
        provider="openai",
        openai_api_key="test-key",
        openai_model="configured-model",
        request_timeout=12,
    )

    with patch("infrastructure.ai.client.OpenAIProvider") as provider_type:
        provider = create_ai_provider(settings)

    assert provider is provider_type.return_value
    provider_type.assert_called_once_with(
        api_key="test-key",
        model="configured-model",
        timeout=12,
        embedding_model="text-embedding-3-small",
    )


def test_provider_factory_rejects_unsupported_provider():
    settings = AISettings(
        provider="other",
        openai_api_key="test-key",
        openai_model="model",
        request_timeout=12,
    )

    with pytest.raises(AIConfigurationError, match="Unsupported AI provider"):
        create_ai_provider(settings)


def test_provider_factory_rejects_missing_credentials():
    settings = AISettings(
        provider="openai",
        openai_api_key=None,
        openai_model="model",
        request_timeout=12,
    )

    with pytest.raises(AIConfigurationError, match="OPENAI_API_KEY"):
        create_ai_provider(settings)


def test_provider_factory_maps_invalid_environment_configuration(monkeypatch):
    monkeypatch.setenv("AI_REQUEST_TIMEOUT", "not-a-number")

    with pytest.raises(AIConfigurationError, match="configuration is invalid"):
        create_ai_provider()


def test_ai_settings_are_environment_driven(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", " OPENAI ")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT", "17.5")

    settings = get_ai_settings()

    assert settings == AISettings(
        provider="openai",
        openai_api_key="env-key",
        openai_model="env-model",
        request_timeout=17.5,
    )
