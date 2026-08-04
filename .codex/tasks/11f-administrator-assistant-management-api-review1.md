# PR 11F Follow-up — Complete Administrator Assistant Management API Requirements

## Repository state

Expected branch:

`feature/11f-administrator-assistant-management-api`

Base branch:

`main`

Pull request:

`#62 — PR 11F — Add Administrator Assistant Management API`

Worktree:

Use the backend worktree already containing PR #62.

Do not create a new branch.

Do not replace or reimplement the existing PR from scratch. Extend and correct the current implementation so it satisfies the original PR 11F specification.

Before making changes:

- confirm the current branch is `feature/11f-administrator-assistant-management-api`;
- confirm the branch contains the existing PR #62 implementation;
- inspect the full diff against `main`;
- preserve correct existing behaviour;
- avoid unrelated refactors.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/11f-administrator-assistant-management-api.md`
- `apps/backend/assistant/domain/assistant.py`
- `apps/backend/assistant/domain/assistant_repository.py`
- `apps/backend/assistant/application/assistant_admin_service.py`
- `apps/backend/assistant/api/assistant_admin.py`
- `apps/backend/assistant/schemas/assistant_admin.py`
- `apps/backend/assistant/infrastructure/repositories/assistant.py`
- `apps/backend/assistant/application/public_chat.py`
- existing administrator authentication and trusted-origin tests;
- existing knowledge-source API and repository tests;
- existing PostgreSQL concurrency tests;
- existing migration conventions;
- existing API error response conventions;
- existing structured logging and metrics conventions.

---

## Objective

Complete the outstanding PR 11F requirements inside PR #62.

The current implementation already provides the basic administrator assistant-management API. This task must harden it so the PR has:

- complete assistant dependency protection;
- verified transaction-safe deletion;
- typed repository boundaries;
- correct exception and metrics semantics;
- precise PostgreSQL uniqueness handling;
- consistent API error contracts;
- full administrator API coverage;
- PostgreSQL repository and concurrency coverage;
- public-chat regression coverage;
- knowledge-source compatibility coverage;
- observability coverage;
- truthful validation evidence.

The result must be production-ready rather than only happy-path complete.

---

## Existing implementation to preserve

The current PR already includes:

- administrator assistant list endpoint;
- assistant detail endpoint;
- assistant creation endpoint;
- assistant partial-update endpoint;
- assistant deletion endpoint;
- default `inactive` and `private` creation state;
- immutable slug behaviour;
- assistant name normalization;
- explicit domain mutation methods;
- timestamp-based optimistic concurrency;
- Redmoor assistant deletion protection;
- administrator session protection;
- trusted-origin protection for writes;
- deterministic pagination;
- public-chat repository protocol narrowing;
- initial lifecycle metrics and logs;
- in-memory service tests.

Preserve these behaviours unless a correction is explicitly required below.

---

## Required implementation

## 1. Complete assistant dependency discovery

The current deletion implementation checks only:

- `knowledge_sources`;
- `documents`;
- `chunks`.

Inspect the complete PostgreSQL schema and identify every persisted record that can belong to an assistant, either directly through `assistant_id` or indirectly through an assistant-owned document, knowledge source or ingestion job.

At minimum, inspect:

- `knowledge_sources`;
- `documents`;
- `chunks`;
- `document_ingestion_jobs`;
- ingestion step execution history;
- ingestion persistence results or receipts;
- file-ingestion requests;
- document fingerprints;
- upload or managed-source metadata;
- audit records;
- evaluation records;
- any assistant-scoped operational records;
- any other table with an `assistant_id`, `document_id`, `knowledge_source_id` or `ingestion_job_id` relationship.

Determine which records are already covered indirectly because a parent document or knowledge source must exist.

Do not add redundant SQL for indirect dependencies where an existing parent dependency already guarantees deletion must be blocked. Document that reasoning in code comments or tests where it is not obvious.

The repository must expose a dependency summary that accurately reflects whether deletion is allowed.

The assistant detail endpoint must never return:

```json
{
  "deletion_allowed": true
}
```

when any persisted assistant-owned state would make deletion unsafe or invalid.

### Dependency summary

Retain `knowledge_source_count`.

Add further counts only where they provide real value to the administrator UI and can be calculated efficiently.

At minimum, `has_dependencies` or its replacement must consider every deletion-blocking ownership path.

Use direct SQL existence checks or a single efficient aggregate query.

Do not load or scan complete collections in application code.

---

## 2. Make deletion demonstrably transaction-safe

Deletion must atomically:

1. lock the assistant row;
2. confirm the assistant exists;
3. check all deletion-blocking dependencies;
4. delete only when no dependencies exist;
5. commit the transaction.

The dependency check and delete must use the same database connection and transaction.

Verify the repository’s connection context manager behaviour. Do not assume it commits or rolls back correctly without inspection.

### Concurrency behaviour

Add real PostgreSQL tests using two independent connections.

Cover at least:

#### Concurrent dependent insertion

- Transaction A begins assistant deletion and locks the assistant.
- Transaction B attempts to create a knowledge source or document for the same assistant.
- The final outcome must preserve referential integrity.
- It must not be possible for the assistant to be deleted while a dependent record is successfully committed.
- No orphan record may remain.

#### Existing dependency

- An assistant with an existing dependency cannot be deleted.
- The assistant and all dependent records remain unchanged.

#### Unused assistant

- An assistant with no dependencies is deleted.
- A subsequent lookup returns not found.

#### Rollback safety

- Force a database failure after dependency validation but before successful completion.
- Verify the assistant remains present.
- Verify no partial deletion occurs.

Use the repository’s existing PostgreSQL concurrency-test patterns and timeout safeguards.

Do not write timing-dependent sleep-based tests where explicit barriers or synchronization primitives can be used.

---

## 3. Fully type the repository contract

Update `AssistantRepository` and both implementations so every new method has explicit parameter and return types.

Do not leave public repository methods with untyped arguments.

Expected typed capabilities include:

```python
def create(self, assistant: Assistant) -> Assistant: ...

def list(
    self,
    *,
    limit: int,
    offset: int,
    status: AssistantStatus | None = None,
    visibility: AssistantVisibility | None = None,
) -> tuple[list[Assistant], int]: ...

def update(
    self,
    assistant: Assistant,
    *,
    expected_updated_at: datetime,
) -> Assistant: ...

def dependency_count(self, assistant_id: UUID) -> int: ...

def has_dependencies(self, assistant_id: UUID) -> bool: ...

def delete(self, assistant_id: UUID) -> None: ...
```

Use a named result dataclass instead of a tuple if that better matches repository conventions.

Also type:

- service parameters;
- service return values;
- helper functions;
- API mapper helpers;
- metric helper names where practical.

Ensure mypy checks the in-memory and PostgreSQL implementations against the protocol.

---

## 4. Correct exception classification

The current service counts every creation or update exception as a conflict.

Replace broad exception classification with explicit handling.

### Creation conflicts

Only increment a conflict metric for expected conflict exceptions such as:

- `DuplicateAssistantSlug`.

Unexpected exceptions must not be labeled as conflicts.

They may:

- increment a separate failure metric if that follows existing conventions;
- otherwise propagate without emitting misleading outcome telemetry.

### Update conflicts

Only classify expected update conflicts as conflicts:

- `AssistantConcurrentUpdate`.

Do not classify:

- database connectivity failures;
- programming errors;
- serialization errors;
- unexpected repository exceptions

as update conflicts.

### Delete conflicts

Classify as expected conflicts:

- `ProtectedAssistantDeletion`;
- `AssistantDeletionBlocked`.

Missing assistants should follow the repository’s normal not-found telemetry convention, not conflict telemetry unless the existing project explicitly treats them as conflicts.

### Metric design

Prefer a single operation counter with bounded labels if this matches the existing metrics architecture:

- operation: `create`, `update`, `delete`;
- outcome: `success`, `conflict`, `not_found`, `failure`.

Do not add assistant IDs, slugs or names as labels.

Telemetry failure must not change API behaviour.

---

## 5. Map PostgreSQL uniqueness errors precisely

The current repository maps every SQLSTATE `23505` error during creation to `DuplicateAssistantSlug`.

This is too broad.

Inspect the exact PostgreSQL unique constraint or index name for assistant slugs.

Map to `DuplicateAssistantSlug` only when the violated constraint is the assistant slug uniqueness constraint.

Do not falsely report a slug conflict for:

- duplicate assistant IDs;
- future unique constraints;
- unrelated database integrity errors.

Use the database driver’s diagnostic fields according to existing repository conventions.

Add PostgreSQL integration tests covering:

- duplicate slug;
- duplicate ID;
- unrelated integrity failure where practical.

A duplicate ID must not be returned as `assistant_slug_conflict`.

---

## 6. Align API errors with existing contracts

Inspect existing administrator APIs and shared error schemas.

Do not introduce a parallel error format if the repository already has:

- an error response model;
- an exception mapping utility;
- a standard machine-readable code structure;
- OpenAPI error documentation helpers.

Refactor `assistant_admin.py` to use the canonical mechanism.

Ensure consistent responses for:

- assistant not found;
- duplicate slug;
- stale update;
- protected assistant;
- assistant with dependencies;
- invalid update;
- authentication failure;
- trusted-origin failure;
- request validation failure.

Do not expose raw domain exception messages where that would produce inconsistent or overly detailed API responses.

### Validation status codes

Follow the repository’s established conventions for validation.

Do not manually convert domain validation to `400` if comparable APIs consistently return `422`.

Whichever convention is used must be:

- consistent;
- tested;
- documented in OpenAPI.

---

## 7. Add complete administrator API tests

Create or extend API tests covering every route.

Use the existing FastAPI application fixture and administrator authentication setup.

At minimum cover:

### Authentication

For every assistant-management route:

- unauthenticated request is rejected;
- non-administrator request is rejected if roles are supported;
- authenticated administrator is accepted.

For all write routes:

- untrusted origin is rejected;
- trusted origin is accepted.

### List

- default pagination;
- bounded maximum limit;
- invalid limit;
- invalid offset;
- deterministic ordering;
- stable ID tie-breaker;
- status filtering;
- visibility filtering;
- combined filtering;
- empty result;
- response pagination metadata.

### Detail

- existing assistant;
- missing assistant;
- invalid UUID;
- concurrency token present;
- dependency summary present;
- Redmoor deletion not allowed;
- unused assistant deletion allowed;
- dependent assistant deletion not allowed.

### Create

- default `inactive`;
- default `private`;
- explicit status;
- explicit visibility;
- Unicode assistant name;
- surrounding name whitespace normalization;
- invalid slug;
- overlong slug;
- blank name;
- control character rejection;
- overlong name;
- duplicate slug;
- unknown fields rejected;
- `201 Created`;
- `Location` header;
- safe response body.

### Update

- update name only;
- update status only;
- update visibility only;
- update multiple fields;
- slug rejected as an extra field;
- ID rejected as an extra field;
- empty patch rejected;
- missing concurrency token rejected;
- valid concurrency token accepted;
- stale concurrency token returns `409`;
- missing assistant returns `404`;
- response contains a new concurrency token;
- retry behaviour follows the selected concurrency semantics.

### Delete

- unused assistant returns `204`;
- missing assistant returns `404`;
- Redmoor assistant returns `409`;
- dependent assistant returns `409`;
- stable machine-readable error code;
- no response body for successful `204`.

### OpenAPI

Verify:

- all routes are registered;
- authentication requirements appear;
- request and response schemas appear;
- documented status codes include expected conflicts and validation failures;
- immutable slug behaviour and concurrency token semantics are described.

---

## 8. Add PostgreSQL repository tests

Add real PostgreSQL integration coverage for:

- creation;
- default persisted values;
- retrieval by ID;
- retrieval by slug;
- unique slug constraint;
- duplicate-ID distinction;
- deterministic pagination;
- status filtering;
- visibility filtering;
- combined filtering;
- count correctness;
- update success;
- stale update rejection;
- missing assistant update;
- dependency summary;
- dependency-blocked deletion;
- successful deletion;
- transaction rollback;
- concurrent update race;
- concurrent insertion versus deletion.

Use isolated test data and clean up after each test according to repository conventions.

Do not use the in-memory repository to prove PostgreSQL behaviour.

---

## 9. Add public-chat regression tests

The public chat API must allow only assistants that are both:

- active;
- public.

Add or extend tests covering all combinations:

| Status   | Visibility | Expected public chat behaviour |
| -------- | ---------- | ------------------------------ |
| active   | public     | allowed                        |
| inactive | public     | unavailable                    |
| active   | private    | unavailable                    |
| inactive | private    | unavailable                    |
| missing  | n/a        | unavailable                    |

Verify that missing, private and inactive assistants produce equivalently safe public responses.

The response must not reveal:

- whether the assistant exists;
- whether it is private;
- whether it is inactive.

Do not weaken administrator access to inactive or private assistants.

---

## 10. Add knowledge-source compatibility tests

Add regression tests proving that administrator knowledge-source management remains independent from public assistant status and visibility.

Cover:

- create or list knowledge sources for an inactive assistant;
- create or list knowledge sources for a private assistant;
- retrieve knowledge-source details for inactive/private assistants;
- re-ingestion remains available where otherwise valid;
- retrieval-state updates remain available;
- assistant status changes do not alter knowledge-source state;
- assistant visibility changes do not alter knowledge-source state;
- cross-assistant access remains prohibited.

Do not introduce public availability checks into authenticated knowledge-source administration.

---

## 11. Complete observability

Add structured logs for expected lifecycle outcomes:

- assistant created;
- assistant updated;
- assistant activated;
- assistant deactivated;
- assistant visibility changed;
- duplicate slug conflict;
- concurrent update conflict;
- assistant deletion blocked;
- protected Redmoor deletion;
- assistant deleted.

Where consistent with existing policy, include:

- assistant ID;
- assistant slug;
- resulting status;
- resulting visibility;
- administrator ID;
- request or correlation ID;
- safe outcome code.

Do not log:

- cookies;
- session tokens;
- authentication headers;
- complete request bodies;
- assistant names unless explicitly allowed by current policy;
- knowledge-source content;
- document content;
- chunks;
- embeddings.

Add tests that inspect log records and verify sensitive fields are absent.

Add metrics tests covering:

- successful create;
- duplicate create conflict;
- successful update;
- stale update conflict;
- successful delete;
- blocked delete;
- telemetry failure isolation.

---

## 12. Review domain timestamp semantics

The current service forces update timestamps forward by at least one microsecond:

```python
now = max(clock(), current.updated_at + timedelta(microseconds=1))
```

Verify this is compatible with:

- PostgreSQL timestamp precision;
- serialization round trips;
- application clock conventions;
- concurrency token comparisons.

If PostgreSQL truncates precision, this strategy may still produce token collisions or false conflicts.

Use the repository’s established precision normalization if one exists.

Add a PostgreSQL test proving:

- returned concurrency tokens survive API serialization;
- the same value can be used in a subsequent update;
- stale values are rejected;
- rapid consecutive updates receive distinct usable tokens.

Do not switch to a version column unless timestamp-based compare-and-set cannot be made reliable without a migration.

---

## 13. Review idempotency decision

Inspect existing administrator write APIs for an established idempotency-key mechanism.

If no such mechanism exists:

- do not add a generic idempotency subsystem;
- document that assistant creation relies on database slug uniqueness and deterministic `409` handling.

If an existing mechanism does exist:

- integrate assistant creation with it;
- add replay and concurrent-request tests.

Do not silently ignore an established repository convention.

---

## 14. Documentation

Update `apps/backend/README.md` or the canonical API documentation to accurately describe:

- list, detail, create, patch and delete routes;
- administrator session requirements;
- trusted-origin requirements for writes;
- default inactive/private creation;
- slug immutability;
- concurrency token usage;
- stale update conflicts;
- dependency-based deletion restrictions;
- Redmoor deletion protection;
- public availability semantics;
- knowledge-source administration independence;
- idempotency decision;
- error codes.

Do not claim tests or validation passed unless they were actually executed.

---

## Acceptance criteria

- [ ] All new repository methods are explicitly typed.
- [ ] Mypy validates both repository implementations against the protocol.
- [ ] Duplicate slug detection checks the exact PostgreSQL constraint.
- [ ] Duplicate IDs are not reported as slug conflicts.
- [ ] Conflict metrics count only expected conflicts.
- [ ] Unexpected failures are not mislabeled as conflicts.
- [ ] Dependency detection covers every assistant-owned persistence path.
- [ ] Assistant detail never incorrectly reports deletion as allowed.
- [ ] Deletion check and delete occur in one transaction.
- [ ] Concurrent dependent insertion cannot create an orphan or invalid final state.
- [ ] Rollback leaves the assistant intact.
- [ ] Administrator API tests cover every route.
- [ ] Authentication tests cover every route.
- [ ] Trusted-origin tests cover every write route.
- [ ] PostgreSQL repository tests cover uniqueness, filtering, concurrency and deletion.
- [ ] Public chat allows only active/public assistants.
- [ ] Public chat does not disclose private or inactive assistant existence.
- [ ] Knowledge-source administration works for inactive and private assistants.
- [ ] Assistant status and visibility changes do not mutate knowledge.
- [ ] All expected lifecycle conflicts emit safe structured logs.
- [ ] Metrics use bounded labels.
- [ ] Telemetry failures do not affect API outcomes.
- [ ] OpenAPI documents routes, conflicts and concurrency.
- [ ] README documentation matches actual behaviour.
- [ ] Full backend tests pass against PostgreSQL.
- [ ] No required database test is reported as passing when skipped.
- [ ] No frontend changes are introduced.
- [ ] No unrelated refactor is included.

---

## Expected test files

Use existing test locations and naming conventions. Likely additions include:

- `apps/backend/tests/test_assistant_admin_api.py`
- `apps/backend/tests/test_assistant_admin_repository_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_concurrency_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_deletion_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_openapi.py`

Also update relevant existing files for:

- public chat;
- knowledge-source API;
- knowledge-source repository;
- administrator authentication;
- metrics;
- logging;
- migrations, if any schema changes are required.

Do not create duplicate test infrastructure where suitable fixtures already exist.

---

## Verification commands

Inspect current scripts and run the repository’s canonical equivalents.

At minimum:

```bash
cd apps/backend

../../venv/bin/ruff check .
../../venv/bin/ruff format --check .
../../venv/bin/mypy .
```

Run targeted assistant-management tests:

```bash
../../venv/bin/python -m pytest \
  tests/test_assistant_admin_service.py \
  tests/test_assistant_admin_api.py \
  tests/test_assistant_admin_repository_postgres_integration.py \
  tests/test_assistant_admin_concurrency_postgres_integration.py \
  tests/test_assistant_admin_deletion_postgres_integration.py \
  tests/test_assistant_admin_openapi.py \
  -q
```

Run relevant regressions:

```bash
../../venv/bin/python -m pytest \
  tests/test_public_chat*.py \
  tests/test_knowledge_source*.py \
  tests/test_admin_auth*.py \
  -q
```

Run the full backend suite against an isolated PostgreSQL database:

```bash
DATABASE_URL="<isolated-postgresql-test-database>" \
  ../../venv/bin/python -m pytest -q
```

Also run:

```bash
git diff --check
```

If migrations are added, run:

- migration upgrade;
- migration downgrade where supported;
- re-upgrade;
- repeated application according to repository idempotency conventions;
- existing-data preservation checks.

---

## Completion report

At the end, report:

- exact files changed;
- exact commands run;
- test pass counts;
- test skip counts;
- reasons for any skips;
- PostgreSQL version or environment used;
- whether any migration was required;
- the complete assistant dependency paths discovered;
- how concurrent insert versus delete is handled;
- how duplicate constraint mapping works;
- how timestamp concurrency precision is handled;
- whether an existing idempotency mechanism was found;
- any original requirement that could not be completed.

Do not commit, push, merge or create another pull request.
