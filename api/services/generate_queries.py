import json

from openai import OpenAI

client = OpenAI()


def generate_queries(query: str) -> list[str]:
    prompt = f"""
Generate 3 different search queries for retrieving relevant documents.

Rules:
- Each query should use different wording
- Remove question wording
- Convert intent into positive factual terms
- Replace negations (optional, not required) with opposites (required, mandatory)
- Add domain synonyms
- Include relevant context words
- Return 6–12 search terms only
- Return ONLY a JSON array of strings

Example:
[
  "sterilise instruments hygiene protocol",
  "clean medical equipment disinfection staff",
  "sterilization procedures hospital hygiene"
]

User query: 
{query}
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)
    try:
        queries = json.loads(response.output_text.strip())
    except (json.JSONDecodeError, ValueError):
        queries = [query]

    return queries
