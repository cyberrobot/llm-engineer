import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def ask_rag(question: str, chunks: list[dict]) -> dict:
    context = "\n\n".join([f"[Source: {chunk['id']}]\n{chunk['text']}" for chunk in chunks])

    prompt = f"""You are a strict assistant answering only from provided context.

Return ONLY valid JSON in this shape:
{{
    "answer": "Concise answer here.",
    "source_ids": ["chunk-id-1", "chunk-id-2"]
}}

Rules:
- Always use the provided context to answer the question.
- If the answer is not supported by the context, say: "I don't know based on the provided documents."
- Be concise and clear in your answer.
- Do not make up information that is not in the context.

Context:
{context}

Question: 
{question}
"""

    response = client.responses.create(model="gpt-5.4-nano", input=prompt)

    return json.loads(response.output_text.strip())


def estimate_tokens(text: str) -> int:
    # Simple estimation: 1 token ~ 4 characters
    return len(text) // 4
