# Backend

FastAPI backend for the AI Discovery Assistant.

## Run locally

Install dependencies from `requirements.txt`, copy `.env.example` to `.env`, and run:

```sh
python -m uvicorn main:app --reload
```

The canonical application entry point is `main:app`.

## AI configuration

Assistant chat uses the provider selected entirely through environment variables:

- `AI_PROVIDER`: provider identifier; currently `openai` (default)
- `OPENAI_API_KEY`: required when Assistant chat is called
- `OPENAI_MODEL`: model identifier (default: `gpt-5.5`)
- `AI_REQUEST_TIMEOUT`: request timeout in seconds (default: `30`)

The OpenAI client is created lazily, so health endpoints and non-AI workflows can start
without provider credentials. Missing or invalid AI configuration is returned as a service
availability error when chat is requested.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
```
