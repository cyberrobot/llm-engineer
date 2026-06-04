import json

from dotenv import load_dotenv

from api.core.load_prompt import load_prompt
from api.services.openai_client import get_openai_client

load_dotenv()

system_prompt = load_prompt("answer_system.md")


def ask_rag(question: str, chunks: list[dict]) -> dict:
    client = get_openai_client()
    context = "\n\n".join([f"[Source: {chunk['id']}]\n{chunk['text']}" for chunk in chunks])

    prompt = f"""
{system_prompt}

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
