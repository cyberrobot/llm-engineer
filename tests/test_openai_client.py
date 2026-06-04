from unittest.mock import patch

import pytest

import api.services.openai_client as openai_client


@pytest.fixture(autouse=True)
def reset_openai_client():
    openai_client._client = None
    yield
    openai_client._client = None


def test_raises_when_api_key_missing():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError):
            openai_client.get_openai_client()


def test_creates_client_with_api_key():
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("api.services.openai_client.OpenAI") as openai,
    ):
        client = openai_client.get_openai_client()

    openai.assert_called_once_with(api_key="test-key")
    assert client == openai.return_value


def test_reuses_cached_client():
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("api.services.openai_client.OpenAI") as openai,
    ):
        first = openai_client.get_openai_client()
        second = openai_client.get_openai_client()

    openai.assert_called_once_with(api_key="test-key")
    assert first is second
