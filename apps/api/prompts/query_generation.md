#prompts/query_generation.md

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
