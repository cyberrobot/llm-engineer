import json

from openai import OpenAI

from api.services.settings import CHUNK_TOP_K

client = OpenAI()


def rerank_chunks(query: str, chunks: list[dict], top_k: int = CHUNK_TOP_K):
    texts = [c["text"] for c in chunks]

    prompt = f"""
Rank the following chunks by relevance to the query.

Return ONLY a JSON array of indices.

Query:
{query}

Chunks:
"""

    for i, text in enumerate(texts):
        prompt += f"\n[{i}] {text}\n"

        prompt += """
Return the indices of the top most relevant chunks in order, like:
[0, 2, 1]
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)

    content = response.output_text.strip()

    try:
        indices = json.loads(content)
    except:
        indices = list(range(len(chunks)))

    reranked = [chunks[i] for i in indices[:top_k]]

    return reranked
