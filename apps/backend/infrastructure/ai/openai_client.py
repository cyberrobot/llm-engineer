from openai import OpenAI

from core.config import get_openai_api_key

_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client

    if _client is None:
        api_key = get_openai_api_key()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=api_key)

    return _client
