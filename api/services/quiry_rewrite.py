from openai import OpenAI

client = OpenAI()


def rewrite_query(query: str) -> str:
    prompt = f"""
Rewrite the user query into a search query for document retrieval.

Rules:
- Remove question wording
- Convert intent into positive factual terms
- Replace negations (optional, not required) with opposites (required, mandatory)
- Add domain synonyms
- Include relevant context words
- Return 6–12 search terms only
- Return ONLY the search query

Example:
User: Is sterilisation optional for staff?
Search query: sterilisation hygiene protocol required mandatory medical staff instruments

User: Do doctors need to clean equipment?
Search query: clean disinfect sterilise sterilize sterilisation sterilization equipment instruments hygiene protocol medical staff

User query: 
{query}
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)
    return response.output_text.strip()
