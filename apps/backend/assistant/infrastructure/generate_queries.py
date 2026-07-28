import json

from infrastructure.ai.openai_client import get_openai_client
from shared.utilities.prompts import load_prompt

system_prompt = load_prompt("query_generation.md")


def generate_queries(query: str) -> list[str]:
    client = get_openai_client()
    prompt = f"""
{system_prompt}

User query: 
{query}
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)
    try:
        queries = json.loads(response.output_text.strip())
    except (json.JSONDecodeError, ValueError):
        queries = [query]

    return queries


query_cache = {}

MAX_CACHE_SIZE = 100


def generate_queries_cached(query: str) -> list[str]:
    if query in query_cache:
        return query_cache[query]

    queries = generate_queries(query)

    if len(query_cache) > MAX_CACHE_SIZE:
        oldest_query = next(iter(query_cache))
        del query_cache[oldest_query]

    query_cache[query] = queries
    return queries
