# Backend

FastAPI backend for the AI Discovery Assistant.

## Run locally

Install dependencies from `requirements.txt`, copy `.env.example` to `.env`, and run:

```sh
python -m uvicorn main:app --reload
```

The canonical application entry point is `main:app`.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
```
