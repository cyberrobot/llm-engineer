# PR 4A — Extract runnable RAG backend

## Objective

Create an independently runnable `apps/rag-backend` implementation without changing production routing.

## Scope

Keep the standalone FastAPI service and its four RAG/health routes, RAG orchestration, provider and
persistence adapters, administrator protection, operational safeguards, resource cleanup,
PostgreSQL integration coverage, least-privilege roles, and import-boundary enforcement. The service
owns its OpenAI, Redis, knowledge-database, and auth/audit-database configuration.

Add only small service-owned logging initialization that makes request IDs available without logging
secrets, document content, prompts, provider output, SQL, or sensitive exception text.

## Excluded

Do not change RAG UI or production routing, ingress, Railway, proxies, DNS, public Assistant APIs,
widget routing, ingestion, Assistant administration, or legacy RAG routes. Do not alter retrieval
weights, limits, top-K, maximum-distance semantics, fallback answers, schemas, or prompt semantics.

The shared frozen HTTP contract, exhaustive implementation parity, and final process-independence
proof are intentionally deferred to PRs 4B, 4C, and 4D.

## Exit criteria

- The service starts independently and exposes only the required routes.
- Production modules do not import backend implementation modules.
- Service-local and extracted-adapter PostgreSQL tests cover principal behavior and protections.
- `apps/backend` remains the production implementation and no traffic is switched.
- The PR's pytest, PostgreSQL, Ruff, formatting, mypy, and import-boundary checks pass.

## Verification

```bash
git diff --check
cd apps/backend && pytest
cd ../rag-backend
pytest -q tests
pytest -q -o "addopts=" --strict-markers tests/test_postgres_integration.py
ruff check .
ruff format --check .
mypy .
```
