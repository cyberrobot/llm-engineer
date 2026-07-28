import json

from core.config import CHUNK_TOP_K
from infrastructure.ai.openai_client import get_openai_client
from shared.utilities.prompts import load_prompt

system_prompt = load_prompt("rerank_chunks.md")


def rerank_chunks(query: str, chunks: list[dict], top_k: int = CHUNK_TOP_K):
    client = get_openai_client()
    texts = [c["text"] for c in chunks]

    chunk_lines = "\n".join(f"[{i}] {text}" for i, text in enumerate(texts))

    prompt = f"""
{system_prompt}

Query:
{query}

Chunks:
{chunk_lines}
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)

    content = response.output_text.strip()

    try:
        indices = json.loads(content)
    except Exception:
        indices = list(range(len(chunks)))

    reranked = [chunks[i] for i in indices[:top_k]]

    return reranked
