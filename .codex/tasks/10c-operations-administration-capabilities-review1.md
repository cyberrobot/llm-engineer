# PR 10C Review 1 Follow-up — Complete Maintenance Coverage and Required Verification

## Repository state

**Branch:** `feature/10c-operations-admin-capabilities`

**Pull request:** #72 — Add operations administration capabilities

**Base:** `main`

Complete this work on the existing PR #72 branch. Do not create another branch or pull request.

## Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/10c-operations-administration-capabilities.md`
- `apps/backend/main.py`
- `apps/backend/assistant/api/routes.py`
- `apps/backend/assistant/api/chat.py`
- `apps/backend/assistant/api/rag.py`
- `apps/backend/assistant/api/public_chat.py`
- `apps/backend/assistant/api/public_chat_middleware.py`
- `apps/backend/operations/infrastructure/maintenance.py`
- `apps/backend/tests/test_operations_administration_api.py`

## Objective

Close the remaining PR 10C review gaps without redesigning the operations administration domain.

The current PR already correctly provides:

- administrator-authorized cache, audit, maintenance, job, and summary APIs;
- durable success/failure administrative auditing with safe metadata;
- shared PostgreSQL maintenance state for production and staging;
- deterministic PostgreSQL audit browsing and filtering;
- read-only job visibility through the established ingestion repository;
- maintenance handling for the published 11G public-chat endpoint;
- explicit readiness and liveness semantics during maintenance.

Preserve those behaviours.

This follow-up must:

1. enforce maintenance mode across every existing unauthenticated assistant request endpoint;
2. prove that administrator authentication and diagnostic routes remain reachable;
3. add the explicit authorization, cache idempotency, and cache-data-safety coverage required by
   the original specification;
4. update the operations runbook to name the centrally gated public request surface.

No migration, frontend, assistant-behaviour, publishing, ingestion, retrieval, or authentication
redesign is permitted.

## Review findings

### 1. Maintenance mode does not cover all public assistant entry points

`MaintenanceModeMiddleware` currently matches only paths beginning with `/public/assistants/`.

The repository also exposes these unauthenticated assistant request endpoints:

- `POST /assistant/chat`
- `POST /rag-chat`

They remain capable of starting new assistant work while maintenance mode is enabled. This violates
the original requirement that normal public assistant functionality reject new public requests.

### 2. Required cross-endpoint verification is incomplete

The implementation uses a shared router-level authorization dependency, but the original test
matrix explicitly requires anonymous/non-administrator rejection for audit and job visibility as
well as cache administration.

The original matrix also requires direct proof that:

- clearing all cache data repeatedly remains safe;
- clearing a region repeatedly remains safe;
- cache inspection never returns stored cache payloads or secrets;
- administrator authentication remains reachable during maintenance.

Add behaviour-focused tests for these outcomes.

## Required implementation

### Central maintenance classification

Extend the existing `MaintenanceModeMiddleware`; do not add route-local maintenance checks.

When maintenance is enabled, reject new requests to:

- `/public/assistants/{assistant_slug}/chat`
- `/assistant/chat`
- `/rag-chat`

Use the existing generic `503 maintenance_mode` response. Do not expose the configured maintenance
message or any administrator-only state.

Use exact route matching for the legacy endpoints. Do not accidentally block:

- `/assistant/health`
- administrator assistant APIs
- administrator authentication APIs
- `/admin/operations/**`
- `/health`, `/health/live`, or `/health/ready`
- ingestion, maintenance tooling, or internal worker endpoints

Preserve request-correlation and applicable CORS behaviour.

### Required tests

Add tests that fail against PR #72 before the production change and pass after it.

Verify while maintenance is enabled:

1. published public chat returns `503 maintenance_mode`;
2. `/assistant/chat` returns `503 maintenance_mode` without invoking its provider/service;
3. `/rag-chat` returns `503 maintenance_mode` without invoking retrieval/generation;
4. `/assistant/health` is not replaced with a maintenance response;
5. administrator operations remain accessible;
6. administrator authentication remains accessible and is not replaced with a maintenance response;
7. liveness remains `200`;
8. readiness and compatibility health retain their documented maintenance behaviour;
9. public maintenance responses remain generic and preserve request IDs.

Verify operations authorization:

- anonymous audit and job requests are rejected;
- an authenticated ingestion principal cannot access audit or job requests;
- an administrator can access them.

Verify cache behaviour:

- repeated whole-cache clearing succeeds;
- repeated region clearing succeeds;
- inspection exposes metadata only and never includes stored payload or secret values.

## Documentation

Update `apps/backend/docs/operations-administration.md` to list the public assistant endpoints
gated by maintenance mode and the administrator/health surfaces deliberately left reachable.

## Verification

Run, at minimum:

```sh
ruff check apps/backend
ruff format --check apps/backend
mypy apps/backend/operations apps/backend/tests/test_operations_administration_api.py
pytest apps/backend/tests/test_operations_administration_api.py
pytest apps/backend/tests -k "operations or admin or maintenance or cache or audit"
pytest apps/backend/tests -k "assistant or publish or preview"
pytest apps/backend/tests
```

Run the PostgreSQL operations-administration integration test against the local disposable database.
Report any pre-existing tool or dependency failure separately from PR-introduced failures.

## Acceptance criteria

- All existing unauthenticated assistant request endpoints reject new requests during maintenance.
- Maintenance enforcement remains centralized in the existing middleware.
- Administrator authentication, administration APIs, and health probes remain reachable.
- The public maintenance response contains no configured message or sensitive state.
- Audit and job authorization cases are explicitly covered.
- Repeated whole-cache and region clearing are explicitly covered.
- Cache inspection is proven not to expose stored values.
- No unrelated public, administrator, ingestion, retrieval, or publishing contract changes.
- Focused and complete backend tests pass.
- Backend linting and changed-surface type checking pass.
