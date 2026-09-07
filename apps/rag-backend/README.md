# RAG backend

Standalone FastAPI RAG service staged for a later routing cutover. It is not production-routed and
the existing `apps/backend` and `apps/rag-ui` contracts remain unchanged.

Configure `RAG_KNOWLEDGE_DATABASE_URL`, `RAG_AUTH_AUDIT_DATABASE_URL`,
`RAG_OPENAI_API_KEY`, `RAG_REDIS_URL`, and
`RAG_ALLOWED_ORIGINS` using `.env.example`. The service uses the existing administrator session
cookie tables, a separate Redis database/namespace, a 32 KiB request limit, 4,000-character
messages, 20 requests/minute for chat, 60 requests/minute for audit logs, a 45-second request
timeout, and a 30-second provider timeout.

`RAG_KNOWLEDGE_DATABASE_URL` is a read-only credential with access only to the RAG knowledge
schema (`documents` and `chunks`). `RAG_AUTH_AUDIT_DATABASE_URL` is a distinct credential limited
to administrator-session lookup plus `audit_logs` reads/inserts; it must not be granted ingestion,
document, chunk, or administrator-management write privileges.
Apply `auth_audit_role.sql` as the database owner after migrations, then grant its
`rag_auth_audit` group role to the login used by `RAG_AUTH_AUDIT_DATABASE_URL`.

Configuration defaults: `RAG_CHAT_MODEL=gpt-5.4-nano`,
`RAG_AI_PROVIDER=openai`,
`RAG_EMBEDDING_MODEL=text-embedding-3-small`, `RAG_PROVIDER_TIMEOUT_SECONDS=30`,
`RAG_PROVIDER_MAX_RETRIES=2`, `RAG_REQUEST_TIMEOUT_SECONDS=45`,
`RAG_HEALTH_TIMEOUT_SECONDS=2`,
`RAG_ALLOWED_ORIGINS=http://localhost:5173`, and
`RAG_SESSION_COOKIE_NAME=redmoor_admin_session`. `RAG_DISABLE_CACHE` and
`RAG_DISABLE_AUDIT_LOGS` default to `false`; disabling either intentionally removes the respective
side effect. `RAG_REDIS_URL` defaults to `redis://localhost:6379/1`.

Run it beside the legacy backend with:

```sh
uvicorn main:app --app-dir apps/rag-backend --port 8001
```

It intentionally exposes only `/health/live`, `/health/ready`, `/rag-chat`, and `/audit-logs`.
Production routing and the RAG UI base URL remain unchanged during extraction.

Focused tests run with `venv/bin/python -m pytest -q apps/rag-backend/tests`. PostgreSQL-backed
contract and parity tests require the repository's disposable PostgreSQL setup and are not
substitutes for the existing backend contract suite.
