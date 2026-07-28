import numpy as np

from infrastructure.ai.openai_client import get_openai_client


def get_embedding(text: str):
    client = get_openai_client()
    response = client.embeddings.create(model="text-embedding-3-small", input=text)

    return response.data[0].embedding


def get_embeddings(texts: list[str]) -> list[list[float]]:
    client = get_openai_client()
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)

    return [item.embedding for item in response.data]


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
