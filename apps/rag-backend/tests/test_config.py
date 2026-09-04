from dataclasses import replace

import pytest
from config import settings


def test_provider_configuration_accepts_openai():
    replace(settings, ai_provider="openai").validate()


def test_provider_configuration_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="RAG_AI_PROVIDER must be openai"):
        replace(settings, ai_provider="unsupported").validate()
