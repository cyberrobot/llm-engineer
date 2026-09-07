# PR 5 — Establish database and operational ownership

## Repository state

Expected branch:

`5-establish-database-and-operational-ownership`

Base branch:

`main`

Worktree:

Fresh worktree based on current `origin/main`.

Dependencies:

- PR 3 / explicit RAG data contracts must be present.
- PR 4 / independently runnable `apps/rag-backend` must be present.
- `apps/backend` remains the production migration owner for the knowledge schema.
- `apps/rag-backend` must remain independently runnable and must not import Python implementation modules from `apps/backend`.
- Existing `/rag-chat`, `/audit-logs`, public Assistant, ingestion, administrator, and operations contracts in `apps/backend` must remain backward compatible.
- This PR may make `rag-backend` deployable alongside `apps/backend`, but must not require a production RAG traffic cutover.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/TEMPLATE.md`
- `.codex/tasks/3-introduce-explicit-rag-data-contracts.md`
- `.codex/tasks/4-extract-runnable-rag-backend.md`
- `apps/backend/docs/rag-persistence-contract.md`
- `apps/backend/docs/operations-administration.md`
- `apps/backend/docs/legacy-rag-contract.md`
- `apps/backend/README.md`
- `apps/rag-backend/README.md`

### Primary change area

- `apps/rag-backend/`
- `apps/rag-backend/tests/`
- `apps/backend/infrastructure/database/`
- `apps/backend/operations/`
- `apps/backend/tests/`
- deployment/CI configuration relevant to the two backend services
- backend/RAG operational documentation

`apps/admin` is primarily a regression-verification surface, not an implementation target.

### Canonical implementation examples

Database ownership and migrations:

- `apps/backend/infrastructure/database/connection.py`
- `apps/backend/infrastructure/database/migrations/`
- `apps/backend/infrastructure/database/rag_read_role.sql`
- `apps/backend/docs/rag-persistence-contract.md`

Existing RAG runtime database boundaries:

- `apps/rag-backend/config.py`
- `apps/rag-backend/infrastructure.py`
- `apps/rag-backend/auth_audit_role.sql`
- `apps/rag-backend/tests/test_postgres_integration.py`

Maintenance mode:

- `apps/backend/operations/application/administration.py`
- `apps/backend/operations/infrastructure/runtime.py`
- `apps/backend/operations/infrastructure/maintenance.py`
- `apps/backend/operations/api/administration_dependencies.py`
- existing maintenance coverage in backend tests

Health/readiness:

- `apps/backend/api/routes/health.py`
- `apps/backend/tests/test_health_routes.py`
- `apps/rag-backend/main.py`
- `apps/rag-backend/tests/test_main.py`

Deployment:

- `apps/backend/Dockerfile`
- deployment guidance in `apps/backend/README.md`

Observability:

- `apps/backend/core/logging.py`
- `apps/rag-backend/logging_config.py`

Reuse existing approaches where suitable. Do not import backend implementation code into `rag-backend` merely to share them.

### Relevant symbols

Knowledge database ownership:

- `infrastructure.database.connection.init_db`
- `rag_reader`
- `RAG_KNOWLEDGE_DATABASE_URL`
- `PostgresKnowledgeRepository`
- `knowledge_connection`

RAG authentication and auditing:

- `RAG_AUTH_AUDIT_DATABASE_URL`
- `rag_auth_audit`
- `auth_audit_connection`
- `AuditRepository`
- `require_admin`

Maintenance:

- `MaintenanceModeMiddleware`
- `MaintenanceService`
- `PostgresRuntimeStateStore`
- `operations_runtime_state`
- `get_runtime_state_store`

Readiness:

- `Settings.validate`
- `Settings.validate_runtime`
- `/health/live`
- `/health/ready`
- `Cache.ping`

Operational failures:

- `rag_chat_timed_out`
- `rag_chat_failed`
- `audit_log_read_failed`
- provider calls in `Provider.embedding`
- provider calls in `Provider.text`
- repository calls in `PostgresKnowledgeRepository.search`
- `AuditRepository.write`
- rate-limit rejection in RAG HTTP middleware

### Expected change surface

Expected changes should remain focused on:

- explicit database/migration ownership;
- a RAG-owned audit schema/table;
- RAG-only audit migration execution;
- least-privilege runtime credentials;
- maintenance-mode consistency;
- RAG readiness checks;
- structured operational telemetry;
- deployment configuration;
- dashboards/alerts;
- rollback and operations documentation;
- PostgreSQL and failure-isolation tests;
- CI coverage.

### Excluded areas

Do not:

- transfer ownership of `documents` or `chunks` away from `apps/backend`;
- run backend migrations from `apps/rag-backend`;
- run RAG audit migrations from `apps/backend`;
- give `rag-backend` write access to `documents` or `chunks`;
- give the normal RAG runtime database credentials schema-owner or migration privileges;
- rename or delete legacy `public.audit_logs` in a way that breaks `apps/backend`;
- change ingestion persistence or ingestion-worker ownership;
- make `apps/backend` depend on `rag-backend` being healthy;
- make administrator APIs depend on `rag-backend`;
- change Admin API response contracts;
- redesign `apps/admin`;
- change RAG retrieval ranking, weights, top-K, prompts, evaluation semantics, caching semantics, authorization semantics, or HTTP response contracts;
- introduce a second independently writable maintenance-mode state;
- make health probes call OpenAI;
- expose database/provider exception details through readiness or HTTP errors;
- put production database-owner credentials into the `rag-backend` runtime service;
- introduce a new observability vendor or tracing stack when the existing deployment platform already satisfies the requirement;
- switch production RAG traffic merely to prove this PR works.

### Unknowns Codex must verify

Before implementation, verify:

1. Whether production ingress/gateway/proxy configuration exists outside the repository and whether it can enforce maintenance mode across both public Assistant traffic and RAG traffic.

2. Whether Railway or another deployment platform is the current deployment target for `rag-backend`.

3. Whether deployment settings are version-controlled or managed outside Git.

4. What monitoring/alerting backend is actually available in production.

5. Whether dashboards and alerts can be represented as code or must be configured through deployment infrastructure.

6. Whether existing RAG audit history must be retained when traffic eventually moves from `apps/backend` to `apps/rag-backend`.

7. Whether a schema named `rag` already exists.

8. Whether the deployment database owner can run a separate RAG migration job.

9. Whether migration credentials can be supplied only to that migration job rather than the runtime application.

10. Whether `RAG_AUTH_AUDIT_DATABASE_URL` should remain the combined authentication/audit/maintenance-read credential or whether the existing deployment infrastructure already supports further credential separation.

11. Whether `rag_reader` is currently provisioned in staging/production or currently exists only as declarative SQL.

12. Whether Redis isolation is currently achieved through a separate database number, separate instance, key namespace, or a combination.

13. Whether the current RAG CI can run backend migrations followed by RAG integration tests against the same disposable PostgreSQL database.

14. Whether any deployment automation currently assumes every Python application uses `apps/backend/Dockerfile`.

If repository/deployment state contradicts the assumptions in this specification, report the mismatch instead of creating a competing migration, monitoring, or maintenance architecture.

---

## Objective

Make `apps/rag-backend` safe to deploy and operate independently while preserving the existing `apps/backend` and `apps/admin` behaviour.

Database ownership must become explicit:

- `apps/backend` owns migrations for `documents` and `chunks`;
- `rag-backend` receives only read access to that knowledge schema;
- `rag-backend` owns its own RAG audit schema/table and audit migrations;
- runtime credentials must not have migration privileges.

Operational ownership must also become explicit:

- public Assistant and RAG maintenance behaviour remains consistent;
- `rag-backend` exposes reliable liveness/readiness probes;
- important RAG failures and latency are observable;
- deployment and rollback are documented and reproducible;
- failure of `rag-backend` cannot impair ingestion or administrator APIs.

## Current architecture

`apps/backend` currently calls `init_db()` during startup when `DATABASE_URL` is configured.

That migration/bootstrap path owns:

- `documents`;
- `chunks`;
- their retrieval indexes and text-search trigger;
- administrator tables;
- operations runtime state;
- legacy `public.audit_logs`;
- other backend persistence.

PR 3 already introduced `rag_reader`, whose intended privileges are limited to:

- database `CONNECT`;
- schema `USAGE`;
- `SELECT` on `documents`;
- `SELECT` on `chunks`.

`apps/rag-backend` already has a separate:

- `RAG_KNOWLEDGE_DATABASE_URL`;
- `RAG_AUTH_AUDIT_DATABASE_URL`;
- `RAG_REDIS_URL`;
- `RAG_OPENAI_API_KEY`.

It does not currently run migrations.

Its audit repository currently reads and writes the backend-owned `public.audit_logs`, creating a shared schema ownership problem.

The RAG authentication/audit role currently receives:

- limited reads from administrator/session tables;
- reads and inserts on `public.audit_logs`;
- no knowledge-table access.

Maintenance mode is owned administratively by `apps/backend`.

In production/staging the state lives in:

`operations_runtime_state`

The existing backend middleware gates:

- `/public/assistants/{...}/chat`;
- legacy `/rag-chat`.

Health, readiness, and administrator endpoints remain reachable.

`apps/rag-backend` already exposes `/health/live` and `/health/ready`. Readiness validates runtime configuration and tests PostgreSQL/Redis connectivity, but database ownership, schema compatibility and deployment behaviour need to become explicit.

The repository currently has no obvious shared OpenTelemetry/Prometheus tracing stack. Do not create a parallel observability architecture without first verifying the actual deployment monitoring capability.

## Required implementation

### 1. Make `apps/backend` the explicit sole migration owner for RAG knowledge data

Preserve `apps/backend` ownership of:

- `public.documents`;
- `public.chunks`;
- required indexes;
- pgvector configuration;
- text-search trigger/generated behaviour;
- Assistant/retrieval-state schema used by RAG.

`apps/rag-backend` must never:

- create these tables;
- alter these tables;
- drop these tables;
- create their indexes;
- manage their triggers;
- run `apps/backend` migration modules;
- call `apps/backend.infrastructure.database.connection.init_db`;
- receive schema-owner privileges over them.

The standalone service must treat this schema as an external read contract.

Keep `apps/backend/infrastructure/database/rag_read_role.sql` backend-owned because it defines access to backend-owned knowledge objects.

### 2. Use the PR 3 least-privilege knowledge credential in `rag-backend`

`RAG_KNOWLEDGE_DATABASE_URL` must point at a login that inherits the existing `rag_reader` role or an equivalent deployment-managed role with the same effective privileges.

Allowed:

- connect to the database;
- use the required schema;
- `SELECT` from `documents`;
- `SELECT` from `chunks`;
- execute the real hybrid retrieval query.

Denied:

- `INSERT`;
- `UPDATE`;
- `DELETE`;
- `TRUNCATE`;
- `CREATE`;
- `ALTER`;
- `DROP`;
- ingestion-job reads or writes unless separately justified;
- administrator table reads;
- audit writes;
- operations-state writes;
- migration ownership.

Do not fall back to the backend's general-purpose `DATABASE_URL`.

### 3. Move standalone RAG auditing to a RAG-owned schema

Use a dedicated RAG-owned PostgreSQL schema, preferably:

`rag`

and a RAG-owned table:

`rag.audit_logs`

The standalone `AuditRepository` must read/write this table rather than `public.audit_logs`.

Preserve the existing HTTP `/audit-logs` response contract and RAG audit semantics.

The new table must retain the fields required by the standalone implementation, including:

- `id`;
- `timestamp`;
- `user_role`;
- `question`;
- `queries`;
- `reply`;
- `retrieved_chunks`;
- `reranked_chunks`;
- `evaluation`;
- `metrics`.

Do not rename, drop or repurpose `apps/backend`'s existing `public.audit_logs` as part of this PR.

That table remains the legacy backend-owned audit store while legacy `/rag-chat` remains active.

### 4. Give `rag-backend` sole migration ownership of `rag.audit_logs`

Add a service-local migration mechanism under `apps/rag-backend`.

Use the smallest implementation consistent with existing repository migration conventions.

The migration source must live with `rag-backend`; `apps/backend` must not import or execute it.

Migrations must:

- be versioned;
- be deterministic;
- be transactional where PostgreSQL permits;
- be idempotent or maintain explicit migration state;
- create the RAG schema where required;
- create/update `rag.audit_logs`;
- create required indexes;
- leave backend-owned schemas untouched.

Normal `uvicorn` application startup must **not** run RAG audit migrations.

Provide an explicit migration command suitable for a deployment/release job.

If privileged migration credentials are required, introduce a deployment-only configuration such as:

`RAG_MIGRATION_DATABASE_URL`

or use the deployment platform's established equivalent.

The migration credential must not be present in the normal RAG runtime container after deployment where the platform permits separate job/runtime secrets.

### 5. Keep the legacy backend audit table explicitly backend-owned

Document that:

- `public.audit_logs` is owned by `apps/backend`;
- `rag.audit_logs` is owned by `apps/rag-backend`;
- neither service migrates the other's audit table.

Do not attempt a destructive migration of legacy audit history.

If continuity of historical RAG audit records is required at the eventual traffic cutover, define an explicit one-time migration/backfill strategy.

That backfill must be:

- separately executable;
- idempotent;
- observable;
- non-destructive to the legacy source;
- excluded from normal service startup.

If historical continuity is not required, document that decision explicitly.

### 6. Harden the RAG authentication/audit runtime role

Update the RAG runtime grant design to match the new ownership model.

`RAG_AUTH_AUDIT_DATABASE_URL` may retain the existing combined runtime role if further separation is not already supported, but its effective privilege surface must be limited to what the service actually needs.

It may require:

- `SELECT` of only the administrator/session columns used to validate sessions;
- `USAGE` on the RAG schema;
- `SELECT` and `INSERT` on `rag.audit_logs`;
- sequence privileges required for RAG audit IDs;
- read-only access to maintenance state if the application-level maintenance fallback in requirement 8 is used.

It must not receive:

- knowledge-table access;
- administrator management writes;
- session writes;
- operations-state writes;
- ingestion access;
- schema creation;
- audit schema ownership;
- migration privileges;
- database-owner privileges.

Update the existing privilege tests against the effective role, not just textual SQL assertions.

### 7. Add a real cross-service schema compatibility test

Add PostgreSQL integration coverage that proves the standalone RAG service works against the **real schema produced by `apps/backend` migrations**.

The test sequence must conceptually:

1. create/use disposable PostgreSQL;
2. run the real backend migration/bootstrap path;
3. provision the RAG reader grants;
4. run the RAG-owned audit migration;
5. connect through RAG runtime credentials;
6. exercise the standalone knowledge repository;
7. exercise the standalone audit repository.

Do not satisfy this solely with the existing simplified hand-created RAG test schema.

The existing isolated repository tests may remain for focused testing, but at least one CI path must prove cross-service schema compatibility.

Do not break the `rag-backend` production import boundary to achieve this. Test orchestration may invoke the two applications' migration/test commands independently.

### 8. Make maintenance mode consistent across both runtimes

Preferred ownership is the ingress/gateway boundary because maintenance mode is an availability/routing concern shared by multiple services.

First verify whether the production gateway can implement this without creating a second source of truth.

If gateway-level enforcement is available:

- use the backend-owned maintenance state or established gateway control;
- gate public Assistant chat and RAG chat consistently;
- leave administrator and health routes reachable;
- do not add an independent `RAG_MAINTENANCE_MODE` flag.

If gateway-level enforcement is not available in the current deployment, implement the fallback inside `rag-backend`:

- read the existing backend-owned `operations_runtime_state`;
- grant the RAG runtime role `SELECT` only;
- do not allow `rag-backend` to update maintenance state;
- keep the existing Admin operations API as the sole write/control boundary.

### 9. Match the existing maintenance HTTP behaviour

For `/rag-chat`, reproduce the established backend behaviour.

When maintenance is enabled return the established stable `503` maintenance response.

When maintenance state cannot be determined, fail closed with the established maintenance-state-unavailable behaviour.

Preserve:

- `Cache-Control: no-store`;
- correlation/request ID headers;
- applicable CORS behaviour;
- stable non-sensitive response bodies.

Do not gate:

- `/health/live`;
- `/health/ready`;
- `/audit-logs`.

Administrator operations in `apps/backend` must continue to work while maintenance is active.

Do not consume OpenAI quota, perform retrieval, write audit rows, or populate cache for a request rejected by maintenance mode.

### 10. Add cross-service maintenance integration coverage

Add a test proving one maintenance control affects both execution paths.

Using the real persistent maintenance state where practical:

1. disable maintenance;
2. verify backend public Assistant traffic can proceed to its normal boundary;
3. verify standalone RAG traffic can proceed to its normal authentication/RAG boundary;
4. enable maintenance through the existing backend-owned mechanism;
5. verify public Assistant traffic receives the maintenance response;
6. verify standalone `/rag-chat` receives the equivalent maintenance response;
7. verify health endpoints remain reachable;
8. verify administrator APIs remain reachable;
9. disable maintenance and verify both traffic paths recover.

Also cover failure of the shared maintenance-state dependency.

### 11. Strengthen RAG readiness checks

Keep `/health/live` dependency-free.

It must not access:

- PostgreSQL;
- Redis;
- OpenAI;
- filesystem-backed migration work;
- administrator state.

`/health/ready` must validate all required runtime configuration and required runtime dependencies.

At minimum verify:

#### Configuration

- knowledge database URL;
- auth/audit database URL;
- OpenAI API key presence;
- configured model names;
- allowed origin policy;
- positive timeout values;
- required Redis configuration when cache is enabled.

Do not perform an OpenAI API request purely for readiness.

#### PostgreSQL

Verify the knowledge credential can connect and can access the schema required for retrieval.

Prefer a harmless schema/privilege query such as reading zero rows or `LIMIT 0` from the actual required objects rather than only `SELECT 1`.

Verify the auth/audit credential can connect and read the minimum objects needed by authentication/audit/maintenance operation.

Do not perform mutations solely for readiness.

#### Redis

When caching is enabled:

- connect;
- `PING`;
- honour the configured health timeout.

When caching is deliberately disabled, Redis must not make readiness fail.

Readiness failures must return a stable, non-sensitive `503`.

### 12. Preserve timeout and failure isolation

Readiness checks must remain tightly bounded by `RAG_HEALTH_TIMEOUT_SECONDS` or the nearest established equivalent.

Do not let one dependency consume the entire request timeout indefinitely.

A failed readiness check must not:

- crash the process;
- expose connection strings;
- expose Redis URLs;
- expose SQL;
- expose credentials;
- expose raw provider/database exception text.

Liveness must remain healthy when only an external dependency is unavailable.

### 13. Add RAG operational telemetry

Extend `rag-backend` observability using the established production monitoring mechanism.

Do not import `apps/backend/core/logging.py`.

A small service-local structured implementation is acceptable.

Record enough low-cardinality telemetry to derive at least:

- request count;
- response status;
- response latency;
- OpenAI request failures;
- OpenAI request timeouts;
- retrieval failures;
- retrieval timeouts;
- rate-limit rejections;
- audit-write failures;
- readiness dependency failures.

Use stable event/failure categories.

Include the request/correlation ID where appropriate.

Do not record:

- prompts;
- questions;
- complete answers;
- document text;
- chunk text;
- embeddings;
- cookies;
- administrator tokens;
- database URLs;
- OpenAI keys;
- raw provider payloads.

### 14. Instrument response latency

Measure externally observable HTTP latency for RAG requests.

At minimum distinguish:

- `/rag-chat`;
- `/audit-logs`;
- health probes where useful.

Provide latency suitable for p50/p95/p99 monitoring.

Do not create labels containing:

- user-controlled query text;
- request IDs;
- administrator IDs;
- arbitrary exception strings;
- unbounded URL values.

### 15. Instrument OpenAI failures and timeouts

Provider telemetry must distinguish at minimum:

- embedding operations;
- response/text-generation operations;
- provider timeout;
- provider/API failure;
- request-budget/deadline timeout where distinguishable.

Preserve the existing safe HTTP error mapping.

Do not log provider response bodies or credentials.

### 16. Instrument retrieval failures

Record actual retrieval infrastructure failures separately from valid "no matching chunks" results.

A successful search returning zero eligible chunks is not a retrieval failure.

Distinguish where practical:

- database timeout;
- database connectivity failure;
- query/repository failure.

Do not include SQL text in telemetry.

### 17. Instrument rate-limit rejections

Every RAG `429` rejection must emit a low-cardinality operational event/metric.

The instrumentation must not change the frozen rate-limit HTTP contract.

Do not use client IP as an unbounded dashboard dimension.

### 18. Instrument audit-write failures

Failures inserting into `rag.audit_logs` must be visible independently of generic RAG request failures.

Record:

- failure category;
- request/correlation ID;
- duration where useful.

Do not record the audit payload itself.

Audit-write failure telemetry is required even where the HTTP request ultimately maps that failure to an existing generic error response.

### 19. Add operational dashboard coverage

Use the deployment's established monitoring/dashboard system.

At minimum provide panels/views for:

1. RAG request volume and status distribution.
2. `/rag-chat` response p50/p95/p99 latency.
3. OpenAI failure and timeout rate.
4. retrieval failure rate.
5. rate-limit rejection volume.
6. audit-write failures.
7. RAG readiness failures/service availability.

Clearly distinguish `rag-backend` from `apps/backend`.

If dashboards are maintained as code, commit the configuration.

If they are deployment-managed, document:

- dashboard name;
- panel definitions;
- metric/log queries;
- service filter;
- ownership;
- where the configured dashboard lives.

Documentation alone must not be presented as a configured dashboard when the deployment system is accessible and configuration is required.

### 20. Add operational alerts

Configure alerts for at least:

- sustained excessive RAG response latency;
- sustained OpenAI failure/timeout rate;
- retrieval failures;
- excessive rate-limit rejections;
- any sustained audit-write failure;
- prolonged readiness failure.

Use minimum-event thresholds where needed so a single request does not produce misleading percentage alerts.

Exact thresholds must be based on an existing production/staging baseline when available.

If no baseline exists, define conservative initial thresholds, document them, and state that they require post-deployment tuning.

Avoid alerting on ordinary zero-result retrievals.

### 21. Add independent deployment configuration for `rag-backend`

Make `apps/rag-backend` buildable and deployable without using the backend application image.

Add an application-specific Dockerfile or the repository's established equivalent.

The runtime image must contain only what the RAG service requires.

The start command should follow the current service entry point, conceptually:

`uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`

Configure the deployment health check to use:

`/health/ready`

Do not use `/health/live` as the only traffic-readiness gate.

### 22. Document required deployment credentials

Document the complete RAG service configuration, including:

- `RAG_KNOWLEDGE_DATABASE_URL`;
- `RAG_AUTH_AUDIT_DATABASE_URL`;
- RAG migration credential/job configuration where introduced;
- `RAG_OPENAI_API_KEY`;
- `RAG_REDIS_URL`;
- model configuration;
- timeout configuration;
- CORS/origin configuration;
- session cookie configuration;
- cache/audit feature flags.

Clearly identify which values are:

- runtime secrets;
- migration-only secrets;
- non-secret configuration.

Explicitly state that the generic backend `DATABASE_URL` must not be supplied to the RAG runtime as a convenience fallback.

### 23. Define deployment ordering

Document a safe deployment sequence.

At minimum:

1. deploy/run any required `apps/backend` migration first;
2. verify the knowledge schema;
3. apply/verify `rag_reader` effective privileges;
4. run RAG-owned audit migrations using the RAG migration owner;
5. apply/verify RAG runtime grants;
6. deploy `rag-backend`;
7. verify `/health/live`;
8. verify `/health/ready`;
9. perform authenticated staging smoke tests;
10. verify telemetry reaches the dashboard;
11. verify alert configuration;
12. leave production routing unchanged unless a separate cutover change explicitly authorizes it.

A failed RAG deployment must not require rolling back the backend or ingestion service.

### 24. Add a rollback runbook

Add a concise operational rollback runbook.

Cover at minimum:

#### Application rollback

- remove/disable routing to the failed RAG deployment where applicable;
- route RAG traffic to the existing known-good backend path where that cutover mechanism exists;
- redeploy the previously known-good RAG image;
- verify backend ingestion and Admin APIs independently.

#### Database rollback

Prefer forward-compatible/expand-only RAG audit migrations.

Do not instruct operators to roll back `documents` or `chunks` merely because `rag-backend` failed.

Do not destroy new audit records as a routine rollback mechanism.

For a RAG audit migration failure, document:

- whether the failed transaction automatically rolls back;
- how migration state is inspected;
- how to retry safely;
- when a forward-fix is required.

#### Credential rollback

Document how to revoke the RAG runtime login or group membership without affecting the backend's write-capable credentials.

#### Maintenance recovery

Document how to confirm maintenance state and restore normal traffic after rollback.

### 25. Prove `rag-backend` failure isolation

Add tests/configuration checks proving `apps/backend` does not require the new service to:

- start;
- ingest;
- process ingestion jobs;
- authenticate administrators;
- serve administrator APIs;
- expose backend health/readiness;
- modify maintenance state.

Do not add an `apps/backend` startup health dependency on `rag-backend`.

Do not make backend readiness fail merely because RAG is unavailable.

Do not make the Admin application's normal APIs proxy through `rag-backend`.

### 26. Preserve Admin behaviour

No material `apps/admin` implementation change is expected.

Existing Admin workflows must continue using the established backend API.

In particular preserve:

- administrator authentication;
- Dashboard;
- Operations;
- health diagnostics;
- maintenance controls;
- ingestion operations;
- Assistant administration;
- knowledge-source administration.

If deployment or API changes unexpectedly require an Admin code change, stop and verify why before expanding scope.

### 27. Preserve backend behaviour

Existing `apps/backend` behaviour must remain compatible.

At minimum preserve:

- startup;
- database migration execution;
- ingestion;
- ingestion workers;
- administrator authentication;
- administrator APIs;
- operations APIs;
- maintenance API;
- public Assistant API;
- legacy `/rag-chat`;
- legacy `/audit-logs`;
- `/health`;
- `/health/live`;
- `/health/ready`.

Do not modify public or administrator response contracts merely to align implementation structure with `rag-backend`.

### 28. Update architecture and operations documentation

Update the nearest authoritative documentation to state explicitly:

- `apps/backend` owns knowledge migrations;
- `rag-backend` consumes that schema read-only;
- `public.audit_logs` is legacy/backend-owned;
- `rag.audit_logs` is standalone-RAG-owned;
- each audit table has exactly one migration owner;
- migration credentials are not runtime credentials;
- maintenance state has one authoritative owner;
- how `rag-backend` participates in maintenance mode;
- readiness dependency semantics;
- observability/dashboard/alert ownership;
- deployment order;
- rollback procedure;
- failure-isolation guarantees.

Update `docs/architecture/repository-map.md` if required so future changes do not accidentally move or duplicate ownership.

## Acceptance criteria

- [ ] `apps/backend` remains the only migration owner for `documents`.
- [ ] `apps/backend` remains the only migration owner for `chunks`.
- [ ] `apps/rag-backend` does not run or import backend migration code.
- [ ] `RAG_KNOWLEDGE_DATABASE_URL` uses an effective least-privilege read credential.
- [ ] That credential can execute the real RAG retrieval query.
- [ ] That credential cannot mutate `documents` or `chunks`.
- [ ] Standalone RAG auditing uses a RAG-owned schema/table rather than `public.audit_logs`.
- [ ] RAG audit migrations are owned and executed only from the RAG deployment boundary.
- [ ] Normal RAG application startup does not execute migrations.
- [ ] RAG runtime credentials do not have migration/schema-owner privileges.
- [ ] Legacy backend `public.audit_logs` remains operational.
- [ ] Existing backend `/audit-logs` behaviour remains unchanged.
- [ ] Existing backend `/rag-chat` behaviour remains unchanged.
- [ ] Cross-service PostgreSQL tests run `rag-backend` against the real backend-migrated knowledge schema.
- [ ] RAG read-role privilege tests prove writes are denied.
- [ ] RAG authentication/audit role privilege tests prove unrelated backend access is denied.
- [ ] There is one authoritative maintenance state.
- [ ] Public Assistant chat and standalone RAG chat react consistently to maintenance mode.
- [ ] `rag-backend` cannot change maintenance mode.
- [ ] Maintenance responses preserve the stable status/body/header contract.
- [ ] Health and administrator routes remain reachable during maintenance.
- [ ] `/health/live` performs no external dependency access.
- [ ] `/health/ready` validates required RAG configuration.
- [ ] `/health/ready` checks required PostgreSQL access.
- [ ] `/health/ready` checks Redis when caching is enabled.
- [ ] `/health/ready` does not call OpenAI.
- [ ] Readiness failures expose no sensitive infrastructure details.
- [ ] RAG response latency is observable.
- [ ] OpenAI failures and timeouts are observable.
- [ ] Retrieval failures are observable.
- [ ] Rate-limit rejections are observable.
- [ ] Audit-write failures are observable.
- [ ] Required dashboard panels exist in the production/staging monitoring system.
- [ ] Required alerts exist and have documented thresholds.
- [ ] Operational telemetry contains no prompts, user questions, document/chunk contents, credentials or raw provider payloads.
- [ ] `rag-backend` has independent deployment/build configuration.
- [ ] Deployment uses `/health/ready` as its traffic readiness check.
- [ ] Deployment instructions distinguish runtime credentials from migration credentials.
- [ ] A rollback runbook exists.
- [ ] RAG deployment rollback does not require reverting backend knowledge migrations.
- [ ] `apps/backend` starts and operates when `rag-backend` is unavailable.
- [ ] Ingestion continues when `rag-backend` is unavailable.
- [ ] Administrator APIs continue when `rag-backend` is unavailable.
- [ ] Existing `apps/backend` tests remain green.
- [ ] Existing `apps/admin` tests, lint, typecheck and build remain green.
- [ ] RAG focused, PostgreSQL, lint, format, type and import-boundary checks remain green.
- [ ] No production routing cutover is introduced unless separately authorized.

## Tests to add or update

### `apps/rag-backend/tests/test_postgres_integration.py`

Extend PostgreSQL coverage for:

- `rag.audit_logs`;
- RAG-owned migration result;
- audit insertion/read ordering;
- least-privilege auth/audit role;
- maintenance-state read;
- denied maintenance update;
- denied knowledge access through the auth/audit credential;
- denied schema changes.

### RAG migration tests

Add focused migration tests proving:

- empty database/schema upgrade succeeds;
- repeat upgrade is safe;
- expected schema/table/indexes exist;
- migration records/versioning are correct;
- backend-owned knowledge tables are untouched;
- legacy `public.audit_logs` is untouched.

### Cross-service PostgreSQL contract test

Add a CI-executed test that:

- initializes a disposable database using real `apps/backend` migrations;
- provisions the RAG reader;
- runs the standalone RAG audit migration;
- executes standalone retrieval against the backend-created `documents`/`chunks`;
- verifies effective privileges.

Do not replace this with the simplified standalone fixture.

### `apps/rag-backend/tests/test_main.py`

Add/update tests for:

- successful readiness;
- missing configuration;
- knowledge database failure;
- auth/audit database failure;
- missing required table/privilege;
- Redis failure when enabled;
- Redis ignored when disabled;
- dependency failure does not affect liveness;
- maintenance enabled;
- maintenance state unavailable;
- health/audit accessibility during maintenance;
- no provider/retrieval/audit/cache activity on a maintenance rejection.

### Maintenance integration coverage

Add cross-service behaviour proving the same backend-controlled maintenance change gates both traffic paths.

### RAG observability tests

Add focused tests proving events/metrics are emitted for:

- request latency;
- successful status;
- provider failure;
- provider timeout;
- retrieval failure;
- retrieval timeout;
- rate-limit rejection;
- audit-write failure;
- readiness failure.

Also prove sensitive request/provider/database content is absent from emitted telemetry.

### Deployment tests/checks

Where practical verify:

- the RAG container image builds;
- the image starts using its own application code;
- no backend modules are copied/imported as an application dependency;
- health check path is `/health/ready`;
- runtime does not automatically invoke migrations.

### Existing backend tests

Update only where ownership documentation or migration compatibility makes a test change necessary.

Keep the existing backend migration, RAG repository, maintenance and legacy contract tests intact.

### Admin regression verification

No new visual/browser test is required because no material Admin UI change is expected.

Run the existing Admin unit/type/lint/build suite to catch regressions.

## Verification commands

Run the narrowest affected tests first, then the complete affected suites.

```bash
git diff --check
```

Backend:

```bash
cd apps/backend

pytest
ruff check .
ruff format --check .
python -m mypy .
```

Required backend PostgreSQL compatibility coverage:

```bash
cd apps/backend

RAG_REPOSITORY_POSTGRES_REQUIRED=true \
pytest -q -o "addopts=" --strict-markers \
tests/test_rag_knowledge_repository_postgres.py \
tests/test_migrations.py
```

Standalone RAG service:

```bash
cd apps/rag-backend

pytest -q tests

pytest -q -o "addopts=" --strict-markers \
tests/test_postgres_integration.py

pytest -q tests/test_import_boundary.py

ruff check .
ruff format --check .
mypy .
```

Run the new cross-service database ownership/compatibility test using the repository's disposable PostgreSQL configuration.

For example, use the final path introduced by this PR:

```bash
# Replace with the actual test path added by this task.
pytest -q -o "addopts=" --strict-markers \
<cross-service-operational-contract-test>
```

Container verification:

```bash
docker build -t llm-engineer-rag-backend apps/rag-backend
```

If the repository/deployment setup supports a local container smoke test, start the image with disposable PostgreSQL/Redis and verify:

```bash
curl --fail http://localhost:<port>/health/live
curl --fail http://localhost:<port>/health/ready
```

Admin regression checks from the repository root:

```bash
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
```

CI:

- update `.github/workflows/test.yml` where necessary so the real cross-service PostgreSQL ownership contract runs on pull requests;
- keep existing backend and `rag-backend` required jobs passing;
- do not weaken or skip existing PostgreSQL or import-boundary checks.

Operational verification before completion:

- verify effective PostgreSQL grants using the actual RAG runtime roles;
- verify migration credentials are absent from the normal RAG runtime;
- verify maintenance mode against both public Assistant and RAG traffic;
- verify `rag-backend` failure leaves backend ingestion and administrator APIs healthy;
- verify the deployment health check uses `/health/ready`;
- verify dashboard data is arriving;
- verify required alerts are configured;
- exercise the rollback runbook far enough to prove its commands/settings are accurate.

Do not claim any deployment, dashboard, alert or rollback verification passed unless it was actually performed successfully.
