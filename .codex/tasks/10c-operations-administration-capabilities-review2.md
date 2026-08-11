# PR 10C Review 2 Follow-up — Preserve Browser Maintenance Responses and Idempotent Startup

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
- `.codex/tasks/10c-operations-administration-capabilities-review1.md`
- `apps/backend/main.py`
- `apps/backend/operations/infrastructure/maintenance.py`
- `apps/backend/infrastructure/database/connection.py`
- `apps/backend/infrastructure/database/migrations/operations_administration.py`
- `apps/backend/tests/test_operations_administration_api.py`
- `apps/backend/tests/test_operations_administration_migration.py`
- `apps/backend/tests/test_operations_administration_postgres.py`

## Objective

Close the remaining production-runtime findings from the second review of PR #72 without changing
the operations administration API or redesigning maintenance and audit persistence.

Review 1 correctly expanded maintenance enforcement to all current unauthenticated assistant chat
routes and added the missing authorization, idempotency, and payload-safety tests. Preserve those
changes.

This follow-up must:

1. preserve readable CORS responses for browser callers of every maintenance-gated public route;
2. keep request-correlation headers on those responses;
3. make the operations migration idempotent at runtime without dropping and revalidating correct
   constraints on every application startup;
4. retain compatibility with a provisional PR 10C schema that may have the older constraints.

## Review findings

### 1. Legacy maintenance responses bypass global CORS

`MaintenanceModeMiddleware` is currently outside `CORSMiddleware` in the effective ASGI stack.

The published `/public/assistants/{assistant_slug}/chat` route still receives CORS headers because
its dedicated public-chat boundary wraps the response. The newly gated `/assistant/chat` and
`/rag-chat` routes rely on global CORS, which is never reached when maintenance middleware returns
its own `503` response.

Consequently, an allowed browser origin receives the correct status and body but cannot read the
response because `Access-Control-Allow-Origin` is absent.

### 2. Database bootstrap churns audit constraints on every startup

`init_db()` invokes the operations migration on every database-backed application startup.

The migration currently executes unconditional `ALTER TABLE ... DROP CONSTRAINT` followed by
`ALTER TABLE ... ADD CONSTRAINT` statements for the audit result constraint. Once the audit table
contains production history, every restart therefore takes an avoidable table lock and validation
pass even when the correct constraint is already present.

The runtime-state compatibility constraint is also dropped unconditionally instead of only when the
provisional constraint exists.

Migrations in this bootstrap model must converge to the desired schema and become no-ops for
already-correct constraints.

## Required implementation

### Middleware composition

Compose middleware so that:

- request correlation wraps maintenance enforcement and always adds `X-Request-ID`;
- global CORS wraps maintenance enforcement for `/assistant/chat` and `/rag-chat`;
- the dedicated published-chat boundary retains its stricter route-specific CORS policy;
- maintenance remains centralized in `MaintenanceModeMiddleware`;
- CORS preflight behaviour remains controlled by the appropriate CORS boundary;
- administrator, health, ingestion, and internal routes remain unaffected.

Do not duplicate CORS header construction in the maintenance middleware if correct composition can
preserve the established policies.

### Idempotent constraint reconciliation

Update the operations migration so a correct schema does not execute `ALTER TABLE` constraint
changes on repeated bootstrap.

Required behaviour:

- a fresh audit table receives a named constraint allowing `STARTED`, `SUCCESS`, and `FAILURE`;
- an existing correct named constraint is left untouched;
- an existing provisional constraint that lacks `STARTED` is replaced once;
- an existing table missing the named constraint receives it;
- the obsolete provisional runtime-state constraint is dropped only when it exists;
- existing audit rows and maintenance state remain intact;
- downgrade behaviour remains unchanged.

Use PostgreSQL catalog checks and the repository's existing conditional migration conventions.

## Required tests

Add tests that fail against the current PR before production changes.

Verify:

1. allowed-origin `/assistant/chat` maintenance responses include the expected CORS origin;
2. allowed-origin `/rag-chat` maintenance responses include the expected CORS origin;
3. both responses retain `X-Request-ID` and the generic maintenance body;
4. published-chat strict CORS behaviour remains unchanged;
5. migration SQL defines the final named audit constraint for fresh tables;
6. migration SQL conditionally inspects existing constraint definitions;
7. repeated migration execution does not contain unconditional top-level audit constraint
   drop/add statements;
8. the obsolete runtime-state constraint is conditionally removed;
9. PostgreSQL initialization and operations persistence tests still pass.

## Exclusions

Do not:

- change endpoint paths or response bodies;
- introduce route-local maintenance checks;
- add a second CORS implementation;
- change audit record fields or query contracts;
- add or remove database tables;
- modify feature flags, assistant behaviour, publishing, ingestion, retrieval, or authentication;
- address unrelated optional load-test typing dependencies.

## Verification

Run, at minimum:

```sh
ruff check apps/backend
ruff format --check apps/backend
mypy apps/backend/operations apps/backend/tests/test_operations_administration_api.py
pytest apps/backend/tests/test_operations_administration_api.py
pytest apps/backend/tests/test_operations_administration_migration.py
pytest apps/backend/tests/test_operations_administration_postgres.py
pytest apps/backend/tests -k "operations or admin or maintenance or cache or audit"
pytest apps/backend/tests -k "assistant or publish or preview"
pytest apps/backend/tests
```

Run the PostgreSQL integration test against the local disposable database rather than accepting a
skip. Report the pre-existing optional `locust` mypy import separately if full-tree mypy is run.

## Acceptance criteria

- Every allowed browser client can read the generic maintenance response from its public route.
- Request correlation and published-chat strict CORS remain intact.
- Repeated database startup leaves correct operations constraints untouched.
- Provisional PR 10C constraints are upgraded safely without deleting data.
- No endpoint or persistence contract changes.
- Focused and complete backend tests pass.
- Backend linting and changed-surface type checking pass.
