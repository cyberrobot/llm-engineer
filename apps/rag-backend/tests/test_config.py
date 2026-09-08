from dataclasses import replace

import pytest

from config import settings


def test_provider_configuration_accepts_openai():
    replace(settings, ai_provider="openai").validate()


def test_provider_configuration_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="RAG_AI_PROVIDER must be openai"):
        replace(settings, ai_provider="unsupported").validate()


def test_health_timeout_must_be_positive():
    with pytest.raises(ValueError, match="RAG timeouts must be positive"):
        replace(settings, health_timeout_seconds=0).validate()


@pytest.mark.parametrize(
    "origins", [(), ("*",), ("javascript:alert(1)",), ("https://user@host",)]
)
def test_allowed_origins_must_be_nonempty_exact_http_origins(origins):
    with pytest.raises(ValueError, match="RAG_ALLOWED_ORIGINS"):
        replace(settings, allowed_origins=origins).validate()
