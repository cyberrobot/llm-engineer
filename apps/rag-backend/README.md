# RAG backend

Standalone FastAPI RAG service staged for a later routing cutover. It is not production-routed and
the existing `apps/backend` and `apps/rag-ui` contracts remain unchanged.

Configure `RAG_DATABASE_URL`, `RAG_OPENAI_API_KEY`, `RAG_REDIS_URL`, and
`RAG_ALLOWED_ORIGINS` using `.env.example`. The service uses the existing administrator session
cookie tables, a separate Redis database/namespace, a 32 KiB request limit, 4,000-character
messages, 20 requests/minute for chat, 60 requests/minute for audit logs, a 45-second request
timeout, and a 30-second provider timeout.

Run it beside the legacy backend with:

```sh
uvicorn main:app --app-dir apps/rag-backend --port 8001
```

It intentionally exposes only `/health/live`, `/health/ready`, `/rag-chat`, and `/audit-logs`.
Production routing and the RAG UI base URL remain unchanged during extraction.

Focused tests run with `venv/bin/python -m pytest -q apps/rag-backend/tests`. PostgreSQL-backed
contract and parity tests require the repository's disposable PostgreSQL setup and are not
substitutes for the existing backend contract suite.
