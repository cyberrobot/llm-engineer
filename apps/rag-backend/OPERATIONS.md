# Standalone RAG operations

## Ownership and credentials

`apps/backend` is the sole migration owner for `public.documents`, `public.chunks`, their
indexes/triggers, administrator/session tables, `public.operations_runtime_state`, and the legacy
`public.audit_logs`. The standalone service consumes knowledge through the backend-owned
`rag_reader` group and never runs backend migrations.

`rag_migrator` is the NOLOGIN owner of `rag`, `rag.schema_migrations`, and `rag.audit_logs`.
A database/bootstrap owner applies `migration_owner_role.sql` once. A separate deployment-only
LOGIN inherits `rag_migrator` and is supplied through `RAG_MIGRATION_DATABASE_URL`; the migration
command explicitly assumes the owner role so objects never belong to the LOGIN. The owner role can
create objects only in `rag` and has no access to backend knowledge tables. Normal `uvicorn` startup
never migrates or performs DDL. Run `python migrations.py status` with the same deployment-only
credential to inspect state. For a non-superuser database/bootstrap owner, a cluster role
administrator must first create the group role with the attributes in `migration_owner_role.sql`
and grant `rag_migrator` to the bootstrap owner with `ADMIN OPTION`. This one-time cluster role
provisioning does not grant the migration LOGIN any runtime access.

Runtime secrets are `RAG_KNOWLEDGE_DATABASE_URL` (a login inheriting only `rag_reader`),
`RAG_AUTH_AUDIT_DATABASE_URL` (a login inheriting only `rag_auth_audit`),
`RAG_OPENAI_API_KEY`, and `RAG_REDIS_URL` when caching is enabled. The migration-only secret is
`RAG_MIGRATION_DATABASE_URL`. Non-secret settings are the provider/model names, retry and timeout
values, allowed origins, session cookie name, and cache/audit feature flags. Never give this service
the backend's generic `DATABASE_URL` as a fallback.

`rag_auth_audit` can read only the administrator/session columns used for validation, read the
single maintenance boolean, and select/insert RAG audit records. It cannot read knowledge,
administer users/sessions, update maintenance, create schema objects, or migrate.

There is no automatic legacy audit backfill. `public.audit_logs` remains intact and queryable by the
legacy backend. Staging deployment does not require historical continuity because production routing
does not change. Any later cutover requiring continuity needs a separately reviewed, idempotent,
non-destructive copy job with counts/checkpoints; it must never run during application startup.

## Deployment order

1. As the database/bootstrap owner, run the normal backend migration and verify
   `public.documents`/`public.chunks`.
2. Have the cluster role administrator provision `rag_migrator` and grant it to the non-superuser
   database/bootstrap owner with `ADMIN OPTION`. As that bootstrap owner, apply
   `apps/backend/infrastructure/database/rag_read_role.sql` and
   `apps/rag-backend/migration_owner_role.sql`.
3. Create distinct LOGIN roles for migration, knowledge reads, and auth/audit. Grant the migration
   LOGIN only `rag_migrator`, and grant the knowledge LOGIN only `rag_reader`.
4. Run `RAG_MIGRATION_DATABASE_URL=... python migrations.py upgrade` with the migration LOGIN.
   Verify `rag` objects are owned by `rag_migrator`, not by that LOGIN.
5. As the bootstrap owner, apply `auth_audit_role.sql`, then grant only `rag_auth_audit` to the
   auth/audit LOGIN. Verify effective privileges through all three actual logins.
6. Build `docker build -t llm-engineer-rag-backend apps/rag-backend` and deploy that image with only
   runtime settings/secrets. Configure the traffic health check as `/health/ready`.
7. Verify `/health/live`, then `/health/ready`, then authenticated staging chat/audit behavior.
8. Verify structured events reach the dashboard and exercise alert test notifications.
9. Leave production routing unchanged unless a separate cutover explicitly authorizes it.

The repository contains no Railway service manifest, gateway configuration, or monitoring-as-code.
Those settings are deployment-managed. This change therefore uses the application fallback for
maintenance: RAG reads backend-owned `operations_runtime_state`; the existing Admin Operations API
remains its only writer.

## Telemetry, dashboard, and alerts

The service emits JSON logs with `service=rag-backend`, a stable event, safe low-cardinality fields,
duration, status, and request ID. Every provider attempt emits `provider_request_completed` with
`operation`, `outcome` (`success`, `timeout`, or `failure`), `failure_category` when applicable, and
`duration_ms`, providing a denominator for rate calculations. It never emits prompts, questions,
answers, chunks, embeddings, cookies, credentials, database URLs, SQL, provider payloads, or raw
exceptions. Stable events are `http_request_completed`, `provider_request_completed`,
`provider_request_failed`, `retrieval_failed`, `rate_limit_rejected`, `audit_write_failed`,
`readiness_check_failed`, `rag_chat_timed_out`, and `rag_chat_failed`.

Deployment owners must create dashboard **RAG Backend Operations** in the platform-managed
monitoring workspace, filtered by `service="rag-backend"`:

| Panel | Query/grouping |
| --- | --- |
| Request volume/status | count `http_request_completed`, grouped by `path,status_code` |
| Chat p50/p95/p99 | percentile `duration_ms` where `path="/rag-chat"` |
| Provider volume/outcomes | count `provider_request_completed`, grouped by `operation,outcome,failure_category` |
| Retrieval failures | rate `retrieval_failed`, grouped by `failure_category` |
| Rate limiting | count `rate_limit_rejected`, grouped by `path` |
| Audit failures | count `audit_write_failed`, grouped by `failure_category` |
| Availability | count `readiness_check_failed` plus deployment-ready instance count |

No production baseline is stored in the repository. Start with conservative five-minute alerts:
p95 chat latency above 10 seconds with at least 20 chats; provider failure/timeout completions
divided by all provider completions above 10% with at least 20 provider operations; at least 5
retrieval failures; at least 100 rate-limit rejections; at least 2 audit-write failures; and
readiness unavailable continuously for 5 minutes. The platform operations owner must tune these
after seven days of staging data. This document is a configuration contract. The repository and
this PR do not install or verify deployment-managed dashboards, alert rules, or notification
delivery; those remain an explicit external deployment follow-up.

## Rollback

Remove or disable standalone RAG routing first (if separately enabled) and retain/restore the
known-good backend RAG path. Redeploy the previous RAG image and independently verify backend
`/health/ready`, ingestion, administrator login/APIs, and maintenance control. RAG failure must not
trigger rollback of backend knowledge migrations.

RAG migrations are expand-only and transactional. A failed transaction leaves neither its schema
change nor version row committed. Inspect with `python migrations.py status`, correct the cause, and
retry `upgrade`; use a forward fix once a version has committed. Never destroy new audit rows as
routine rollback.

Credential rollback is `REVOKE rag_reader FROM <knowledge_login>` and/or
`REVOKE rag_auth_audit FROM <auth_audit_login>`, followed by login disable/secret revocation in the
deployment platform. Do not alter backend credentials. Confirm maintenance through
`GET /admin/operations/maintenance`; restore it only through the existing Admin Operations API and
verify both traffic paths after recovery.
