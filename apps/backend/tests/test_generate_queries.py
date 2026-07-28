from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from assistant.infrastructure.generate_queries import (
    generate_queries,
    generate_queries_cached,
    query_cache,
)


@pytest.fixture(autouse=True)
def clear_query_cache():
    query_cache.clear()
    yield
    query_cache.clear()


def test_generate_queries_uses_openai_client():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(output_text='["query one", "query two"]')

    with patch("assistant.infrastructure.generate_queries.get_openai_client", return_value=client):
        result = generate_queries("original query")

    assert result == ["query one", "query two"]
    client.responses.create.assert_called_once()


def test_generate_queries_falls_back_to_original_query_for_invalid_json():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(output_text="not json")

    with patch("assistant.infrastructure.generate_queries.get_openai_client", return_value=client):
        result = generate_queries("original query")

    assert result == ["original query"]


def test_generate_queries_cached_reuses_cached_result():
    with patch(
        "assistant.infrastructure.generate_queries.generate_queries",
        return_value=["expanded query"],
    ) as generate_queries_mock:
        first = generate_queries_cached("original query")
        second = generate_queries_cached("original query")

    assert first == ["expanded query"]
    assert second == ["expanded query"]
    generate_queries_mock.assert_called_once_with("original query")
