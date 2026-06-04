import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from api.services.generate_queries import generate_queries, generate_queries_cached, query_cache


class GenerateQueriesTest(unittest.TestCase):
    def setUp(self):
        query_cache.clear()

    def tearDown(self):
        query_cache.clear()

    def test_generate_queries_uses_openai_client(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text='["query one", "query two"]'
        )

        with patch("api.services.generate_queries.get_openai_client", return_value=client):
            result = generate_queries("original query")

        self.assertEqual(result, ["query one", "query two"])
        client.responses.create.assert_called_once()

    def test_generate_queries_falls_back_to_original_query_for_invalid_json(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text="not json")

        with patch("api.services.generate_queries.get_openai_client", return_value=client):
            result = generate_queries("original query")

        self.assertEqual(result, ["original query"])

    def test_generate_queries_cached_reuses_cached_result(self):
        with patch(
            "api.services.generate_queries.generate_queries",
            return_value=["expanded query"],
        ) as generate_queries_mock:
            first = generate_queries_cached("original query")
            second = generate_queries_cached("original query")

        self.assertEqual(first, ["expanded query"])
        self.assertEqual(second, ["expanded query"])
        generate_queries_mock.assert_called_once_with("original query")


if __name__ == "__main__":
    unittest.main()
