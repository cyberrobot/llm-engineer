# PR 11F Review 2 Follow-up — Complete Remaining Assistant Management Requirements

## Repository state

Expected branch:

`feature/11f-administrator-assistant-management-api`

Base branch:

`main`

Pull request:

`#62 — PR 11F — Add Administrator Assistant Management API`

Worktree:

Use the existing backend worktree containing PR #62.

Do not create a new branch.

Do not replace the current implementation. Make the smallest focused changes needed to satisfy the remaining PR 11F requirements.

Before changing code:

- confirm the current branch is `feature/11f-administrator-assistant-management-api`;
- confirm the current HEAD matches the latest open PR #62 branch;
- inspect the complete diff against `main`;
- preserve already-correct behaviour;
- avoid unrelated refactors.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/11f-administrator-assistant-management-api.md`
- `.codex/tasks/11f-administrator-assistant-management-api-review1.md`
- `apps/backend/assistant/infrastructure/repositories/assistant.py`
- `apps/backend/assistant/application/assistant_admin_service.py`
- `apps/backend/assistant/api/assistant_admin.py`
- `apps/backend/assistant/application/public_chat.py`
- `apps/backend/tests/test_assistant_admin_api.py`
- `apps/backend/tests/test_assistant_admin_repository_postgres_integration.py`
- existing public-chat tests;
- existing knowledge-source API and service tests;
- existing PostgreSQL concurrency tests;
- existing logging and metrics tests;
- database migrations defining assistant, document, knowledge-source and ingestion relationships.

---

## Objective

Complete the remaining requirements identified during the second review of PR #62.

The current implementation already provides the main administrator assistant-management API and has corrected several earlier issues. This task must close the remaining gaps in:

- transaction-safe assistant deletion;
- rollback safety;
- dependency-path verification;
- public-chat lifecycle regression coverage;
- knowledge-source compatibility;
- API deletion-conflict coverage;
- deterministic validation contracts;
- deterministic PostgreSQL pagination tests;
- metrics and structured logging tests;
- PostgreSQL-backed API concurrency-token verification;
- truthful validation reporting.

The final result must demonstrate the required behaviour with reliable automated tests, not only comments or assumptions.

---

## Existing implementation to preserve

Preserve the current correct behaviour, including:

- list, detail, create, patch and delete administrator routes;
- administrator session protection;
- trusted-origin protection for writes;
- inactive/private defaults;
- immutable assistant slugs;
- Unicode assistant names;
- name trimming and control-character rejection;
- deterministic repository ordering by creation timestamp and ID;
- timestamp-based optimistic concurrency;
- Redmoor deletion protection;
- duplicate-slug mapping by PostgreSQL constraint name;
- typed repository contracts;
- typed dependency summary;
- bounded operation/outcome metrics;
- explicit conflict, not-found and failure handling;
- current shared API exception contract;
- existing OpenAPI documentation;
- public chat limited to active/public assistants.

Do not weaken or remove existing coverage.

---

## Required implementation

## 1. Add PostgreSQL concurrent insert-versus-delete coverage

Add a real PostgreSQL integration test proving assistant deletion remains safe when a concurrent transaction attempts to create a dependent record.

Use two independent PostgreSQL connections and explicit synchronization.

Do not use arbitrary sleeps as the primary synchronization mechanism.

### Required scenario

1. Create an unused non-Redmoor assistant.
2. Transaction A begins deletion and locks the assistant row using the production repository path or equivalent production SQL.
3. Pause Transaction A after the assistant row is locked but before deletion is committed.
4. Transaction B attempts to insert a dependent record for the same assistant.

Prefer a direct dependency with a real foreign key to `assistants`, such as:

- a knowledge source; or
- a document.

5. Release Transaction A.
6. Verify the final outcome is deterministic and referentially valid.

Acceptable outcomes depend on the existing database constraints and transaction ordering:

- deletion succeeds and the dependent insert fails; or
- the dependent insert succeeds first and deletion is blocked.

The following outcomes are never acceptable:

- assistant deleted while dependent row commits;
- orphaned dependent row;
- partial transaction state;
- silent integrity violation.

### Test requirements

The test must:

- use separate database connections;
- use explicit events, barriers or locks to coordinate execution;
- use bounded timeouts;
- fail clearly on deadlock or indefinite blocking;
- clean up all data;
- assert final database state directly.

Use the repository’s existing concurrency-test patterns where available.

---

## 2. Add deletion rollback-safety coverage

Add a PostgreSQL integration test proving that a failure after dependency validation does not partially delete the assistant.

### Preferred implementation

Introduce the smallest test seam consistent with existing architecture, for example:

- a repository subclass used only in tests;
- an injected hook or cursor wrapper;
- a deliberately triggered database error after the dependency check but before commit.

Do not add production complexity solely for testing if an existing transaction test pattern can cover this.

### Required assertions

After the forced failure:

- the assistant still exists;
- no dependent records are removed;
- the transaction is rolled back;
- a subsequent repository operation can use the connection normally;
- no partial state remains.

Do not catch and suppress the forced error in production code.

---

## 3. Prove indirect dependency coverage

The repository currently documents that ingestion and persistence records are anchored through documents or knowledge sources.

Add tests that prove this assumption for representative indirect records.

Inspect the schema and select at least one representative record from relevant categories, such as:

- `document_ingestion_jobs`;
- ingestion step execution history;
- ingestion persistence results;
- file-ingestion requests;
- fingerprints or managed-source metadata.

### Required behaviour

For each selected indirect category:

- create the required parent document or knowledge source for an assistant;
- create the indirect child record using the canonical repository or valid SQL fixture;
- verify assistant deletion is blocked because the parent document or knowledge source exists;
- verify the detail dependency summary reports deletion as unavailable;
- verify removing only the indirect child does not make deletion available while the parent remains;
- verify no child can legally exist after its required parent is removed.

Do not expand the production dependency SQL to every indirect table unless schema inspection proves a direct assistant ownership path is missing.

Where indirect coverage is guaranteed by a foreign key, make the test and code comment explicit.

---

## 4. Add complete public-chat lifecycle regression tests

Extend the existing public-chat test suite.

Cover every assistant lifecycle combination:

| Status   | Visibility     | Expected result  |
| -------- | -------------- | ---------------- |
| active   | public         | request proceeds |
| inactive | public         | unavailable      |
| active   | private        | unavailable      |
| inactive | private        | unavailable      |
| missing  | not applicable | unavailable      |

### Safe response equivalence

For inactive, private and missing assistants, verify the public response does not reveal:

- whether the assistant exists;
- whether it is inactive;
- whether it is private;
- internal status or visibility values.

Where practical, assert equivalent:

- status code;
- machine-readable error code;
- response shape;
- safe message.

Do not compare request IDs or other intentionally variable metadata.

### Existing public assistant

Preserve existing Redmoor public-chat behaviour.

Do not make administrator-only assistants publicly accessible.

---

## 5. Add knowledge-source compatibility tests

Extend existing authenticated knowledge-source tests.

Prove that assistant status and visibility affect public availability only.

### Required scenarios

For an authenticated administrator:

- list knowledge sources for an inactive assistant;
- retrieve knowledge-source detail for an inactive assistant;
- create or re-ingest a source for an inactive assistant where otherwise valid;
- list knowledge sources for a private assistant;
- retrieve knowledge-source detail for a private assistant;
- create or re-ingest a source for a private assistant where otherwise valid;
- enable and disable source retrieval for inactive/private assistants;
- preserve cross-assistant isolation.

### Lifecycle mutations

Create an assistant with knowledge sources and then:

1. deactivate it;
2. verify knowledge-source state remains unchanged;
3. make it private;
4. verify knowledge-source state remains unchanged;
5. reactivate or make it public;
6. verify no ingestion or retrieval state was silently rewritten.

Status and visibility updates must not:

- delete sources;
- disable source retrieval;
- trigger ingestion;
- reset ingestion status;
- alter source ownership;
- move sources between assistants.

Use existing service or API fixtures rather than creating a parallel test application.

---

## 6. Complete administrator deletion API coverage

Extend `test_assistant_admin_api.py` or the canonical API test location.

Add explicit tests for:

### Redmoor deletion

`DELETE /admin/assistants/{REDMOOR_ASSISTANT_ID}`

Assert:

- `409 Conflict`;
- stable machine-readable code;
- safe message;
- Redmoor assistant remains present.

### Dependency-blocked deletion

Create an assistant with a real or test-double dependency.

Assert:

- `409 Conflict`;
- stable machine-readable code such as `assistant_has_dependencies`;
- safe message;
- assistant remains present;
- dependency remains present.

### Missing assistant

Keep or add explicit coverage for:

- `404 Not Found`;
- stable error code.

### Successful deletion

Keep explicit assertions for:

- `204 No Content`;
- empty body;
- subsequent detail request returns `404`.

---

## 7. Make validation response codes deterministic

The current API test accepts either `400` or `422` for invalid creation requests.

Replace ambiguous assertions with the repository’s canonical validation behaviour.

Inspect comparable administrator APIs and shared exception handlers.

Choose and enforce one contract.

Likely categories:

- Pydantic request-schema validation: `422`;
- domain validation after schema parsing: use the repository’s established status, consistently.

Do not allow equivalent inputs to randomly produce different status codes depending on which validation layer catches them.

### Required tests

Assert exact status and error code for:

- invalid slug pattern;
- overlong slug;
- blank name;
- overlong name;
- control characters;
- unknown field;
- empty patch;
- immutable slug in patch;
- immutable ID in patch;
- missing concurrency token;
- invalid UUID;
- pagination bounds.

Document any intentional distinction between schema validation and domain validation.

---

## 8. Make PostgreSQL pagination tests isolated and deterministic

The current test uses the shared assistant table and assumes inserted rows appear within a small unfiltered page.

Refactor the test so it cannot fail because of unrelated existing rows.

Use one or more of these approaches:

- unique status/visibility combinations plus filters;
- controlled timestamps newer than all fixture data;
- a sufficiently specific filter;
- an isolated database;
- explicit cleanup before and after the test;
- direct assertion against a query restricted to test-created assistants.

Do not assert:

```python
filtered_total == len(filtered)
```

unless the page limit is proven to include every matching record.

### Required pagination coverage

Add deterministic tests for:

- default ordering;
- equal `created_at` values using assistant ID as tie-breaker;
- offset behaviour;
- limit behaviour;
- total count independent of page size;
- status filtering;
- visibility filtering;
- combined filtering;
- empty result.

Prefer test-created identifiers and slugs that cannot collide with existing fixtures.

---

## 9. Add metrics behaviour tests

Add focused unit tests for `AssistantAdministrationService`.

Verify metric labels for:

- create success;
- duplicate slug conflict;
- create unexpected failure;
- update success;
- stale update conflict;
- update not found;
- update unexpected failure;
- delete success;
- protected deletion conflict;
- dependency-blocked conflict;
- delete not found;
- delete unexpected failure;
- detail not found where currently measured.

Use a fake metric collector or patch the existing metric object according to repository conventions.

Do not assert global Prometheus counter totals that can be affected by other tests unless the registry is isolated.

### Telemetry failure isolation

Force metric emission to raise.

Verify the underlying service operation still:

- succeeds when business logic succeeds;
- raises the original domain/repository exception when business logic fails.

Telemetry failure must never replace the authoritative result.

---

## 10. Add structured logging safety tests

Add tests covering lifecycle and conflict log records.

Verify events are emitted for:

- create success;
- duplicate slug conflict;
- update success;
- activation;
- deactivation;
- visibility change;
- concurrent update conflict;
- protected deletion;
- dependency-blocked deletion;
- successful deletion.

### Safe fields

Verify log records may contain:

- assistant ID;
- assistant slug where allowed;
- status;
- visibility;
- safe outcome code.

Verify log records do not contain:

- assistant name;
- request payload;
- cookie;
- session token;
- authorization header;
- knowledge-source content;
- document content;
- chunk text;
- embeddings.

Use `caplog` or the repository’s standard logging test utilities.

### Logging failure isolation

Force logging to raise.

Verify it does not change the service outcome.

---

## 11. Add PostgreSQL-backed API concurrency-token round-trip test

Add an integration test using:

- the real FastAPI route;
- the real PostgreSQL assistant repository;
- JSON serialization and parsing.

### Required sequence

1. Create an assistant through the API.
2. Fetch assistant detail through the API.
3. Capture the serialized `concurrency_token`.
4. Update through `PATCH` using that token.
5. Verify update succeeds.
6. Capture the new serialized token.
7. Verify it differs from the first token.
8. Send another update using the stale first token.
9. Verify `409 Conflict`.
10. Fetch detail and verify only the successful update persisted.

This test must prove timestamp precision survives:

- PostgreSQL persistence;
- Python datetime conversion;
- Pydantic serialization;
- JSON transport;
- request parsing;
- SQL compare-and-set.

Use an isolated PostgreSQL database or properly namespaced test records.

---

## 12. Complete boundary and API cases

Add missing API coverage for:

### Creation

- explicit `active`;
- explicit `public`;
- explicit inactive/private;
- exactly maximum-length slug;
- slug exceeding maximum length;
- exactly maximum-length name;
- name exceeding maximum length.

### Listing

- multiple assistants;
- deterministic ID tie-breaker;
- offset and limit;
- filters returning no results.

### Update

- name only;
- status only;
- visibility only;
- multiple fields;
- missing concurrency token;
- stale concurrency token;
- new token returned;
- missing assistant;
- rapid consecutive updates.

### Roles

If the administrator authentication model supports multiple roles, add a test proving a valid authenticated non-administrator cannot access the routes.

If the current system has no non-administrator role, document that this test is not applicable rather than inventing one.

---

## 13. OpenAPI verification

Retain existing OpenAPI tests and strengthen them where needed.

Verify:

- list route documents pagination and filters;
- create route documents inactive/private defaults;
- create route documents immutable slug;
- patch route documents concurrency-token requirement;
- delete route documents Redmoor and dependency conflicts;
- error schemas are referenced consistently;
- `201`, `204`, `404`, `409` and `422` responses are present where applicable;
- authentication requirements are visible for all routes;
- trusted-origin behaviour is documented for writes if the project exposes it in OpenAPI.

Do not rely only on free-text substring assertions where schema assertions are possible.

---

## 14. Validation and truthful reporting

Run all required tests against a real PostgreSQL database.

The current PR has no visible commit status checks, so local validation evidence must be precise.

Do not claim:

- PostgreSQL tests passed if they were skipped;
- migration tests passed if none were run;
- full backend suite passed if only targeted tests ran;
- CI passed if no CI status exists.

Where PostgreSQL is required, set:

`ASSISTANT_ADMIN_POSTGRES_REQUIRED=true`

or the repository’s equivalent so missing database access fails instead of skipping.

---

## Acceptance criteria

- [ ] Concurrent dependent insertion versus assistant deletion is covered using two PostgreSQL connections.
- [ ] No assistant can be deleted while a dependent record successfully commits.
- [ ] No orphaned dependent record can remain.
- [ ] Forced deletion failure rolls back completely.
- [ ] Representative indirect ingestion and persistence records are proven to be covered through parent dependencies.
- [ ] Public chat accepts only active/public assistants.
- [ ] Missing, inactive and private assistants return equivalently safe public responses.
- [ ] Knowledge-source administration works for inactive assistants.
- [ ] Knowledge-source administration works for private assistants.
- [ ] Status and visibility changes do not mutate knowledge-source or ingestion state.
- [ ] Redmoor deletion returns a tested `409`.
- [ ] Dependency-blocked deletion returns a tested `409`.
- [ ] Validation responses use deterministic status codes.
- [ ] PostgreSQL pagination tests are isolated and deterministic.
- [ ] ID tie-breaker ordering is tested.
- [ ] Metrics success, conflict, not-found and failure outcomes are tested.
- [ ] Metrics failures do not affect service outcomes.
- [ ] Structured lifecycle and conflict logs are tested.
- [ ] Sensitive data is absent from assistant administration logs.
- [ ] Logging failures do not affect service outcomes.
- [ ] PostgreSQL-backed API concurrency-token round trip is tested.
- [ ] Stale API concurrency tokens return `409`.
- [ ] Maximum-length and over-limit boundaries are tested.
- [ ] OpenAPI accurately documents defaults, concurrency and conflicts.
- [ ] Full backend suite passes against PostgreSQL.
- [ ] No required PostgreSQL test is skipped.
- [ ] No frontend code is changed.
- [ ] No unrelated refactor is introduced.

---

## Expected test changes

Use existing locations and fixtures where possible.

Likely files include:

- `apps/backend/tests/test_assistant_admin_api.py`
- `apps/backend/tests/test_assistant_admin_repository_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_service.py`
- existing public-chat API/service test files;
- existing knowledge-source API/service/integration test files.

Add a new file only where separation materially improves clarity, for example:

- `apps/backend/tests/test_assistant_admin_concurrency_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_observability.py`
- `apps/backend/tests/test_assistant_admin_api_postgres_integration.py`

Do not duplicate existing fixtures or PostgreSQL bootstrap helpers.

---

## Verification commands

Inspect the repository and use the canonical commands.

At minimum:

```bash
cd apps/backend

../../venv/bin/ruff check .
../../venv/bin/ruff format --check .
../../venv/bin/mypy .
```

Run targeted assistant-management tests with PostgreSQL required:

```bash
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest \
  tests/test_assistant_admin_service.py \
  tests/test_assistant_admin_api.py \
  tests/test_assistant_admin_repository_postgres_integration.py \
  tests/test_assistant_admin_concurrency_postgres_integration.py \
  tests/test_assistant_admin_observability.py \
  tests/test_assistant_admin_api_postgres_integration.py \
  -q
```

Use actual filenames after implementation.

Run public-chat regressions:

```bash
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest \
  tests/test_public_chat*.py \
  -q
```

Run knowledge-source regressions:

```bash
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest \
  tests/test_knowledge_source*.py \
  -q
```

Run the complete backend suite:

```bash
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest -q
```

Also run:

```bash
git diff --check
```

If the repository has dedicated OpenAPI, metrics or migration commands, run those as well.

---

## Completion report

At completion, report:

- exact files changed;
- exact commands run;
- pass, fail and skip counts;
- PostgreSQL version and test database used;
- whether any required test skipped;
- result of concurrent insert-versus-delete test;
- result of rollback-safety test;
- indirect dependency paths verified;
- public-chat lifecycle matrix results;
- inactive/private knowledge-source compatibility results;
- exact validation status-code contract;
- metrics and logging tests added;
- API concurrency-token round-trip result;
- any requirement that remains incomplete.

Do not commit, push, merge or create another pull request.
