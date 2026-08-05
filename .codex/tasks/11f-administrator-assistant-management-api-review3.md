# PR 11F Review 3 Follow-up — Close Final Assistant Management Gaps

## Repository state

Expected branch:

`feature/11f-administrator-assistant-management-api`

Base branch:

`main`

Pull request:

`#62 — PR 11F — Add Administrator Assistant Management API`

Use the existing backend worktree and current PR branch.

Do not create a new branch.

Do not redesign the assistant-management implementation. Make only the focused changes required below.

Before editing:

- confirm the current branch;
- confirm the latest PR #62 HEAD;
- inspect the complete diff against `main`;
- preserve existing passing behaviour;
- avoid unrelated refactoring.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `.codex/tasks/11f-administrator-assistant-management-api.md`
- `.codex/tasks/11f-administrator-assistant-management-api-review1.md`
- `.codex/tasks/11f-administrator-assistant-management-api-review2.md`
- `apps/backend/tests/test_knowledge_source_api_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_api_postgres_integration.py`
- `apps/backend/tests/test_assistant_admin_repository_postgres_integration.py`
- existing knowledge-source re-ingestion tests;
- existing cross-assistant isolation tests;
- existing retrieval-state tests.

---

## Objective

Close the final outstanding PR 11F requirements:

1. Prove re-ingestion remains available for inactive and private assistants.
2. Prove retrieval can be disabled and re-enabled independently of assistant lifecycle.
3. Preserve and explicitly verify cross-assistant knowledge-source isolation.
4. Verify dependency-aware assistant detail through the real PostgreSQL-backed API.
5. Make pagination total-count assertions exact and deterministic.
6. Run and truthfully report the complete validation suite.

---

## 1. Complete inactive/private knowledge-source lifecycle tests

Extend the existing PostgreSQL knowledge-source compatibility test.

For both lifecycle configurations:

- inactive/public;
- active/private;

perform the following authenticated administrator workflow:

1. Create a direct-text knowledge source.
2. List sources.
3. Retrieve source detail.
4. Disable retrieval.
5. Verify retrieval state is disabled.
6. Re-enable retrieval.
7. Verify retrieval state is enabled.
8. Trigger re-ingestion.
9. Verify the endpoint accepts the operation using its documented status.
10. Verify a valid ingestion job is created or reused according to existing idempotency behaviour.
11. Verify assistant status and visibility remain unchanged.
12. Verify source ownership remains unchanged.

Do not bypass the API by calling the service directly unless the repository’s existing API tests use that convention.

### Re-ingestion assertions

Assert that re-ingestion:

- does not reject inactive assistants;
- does not reject private assistants;
- remains scoped to the source’s owning assistant;
- creates or reuses only an ingestion job belonging to the correct document;
- does not alter source retrieval state;
- follows existing active-job and idempotency rules.

Use existing re-ingestion fixtures and helpers.

---

## 2. Verify cross-assistant isolation after lifecycle changes

Create two assistants:

- assistant A, inactive or private;
- assistant B, active/public or another contrasting lifecycle state.

Create a knowledge source under assistant A.

Assert that authenticated administrator requests under assistant B cannot:

- retrieve the source;
- update retrieval state;
- trigger re-ingestion;
- delete the source.

Use the existing safe not-found contract rather than exposing cross-assistant ownership.

Then change assistant A’s status and visibility and repeat the isolation assertions.

Lifecycle changes must never weaken assistant scoping.

---

## 3. Add PostgreSQL-backed detail dependency test

Extend `test_assistant_admin_api_postgres_integration.py` or add a focused test.

Required sequence:

1. Create an assistant through the real administrator API.
2. Fetch detail and assert:
   - `knowledge_source_count == 0`;
   - `deletion_allowed is true`.
3. Create a real knowledge source or document owned by that assistant.
4. Fetch assistant detail again.
5. Assert:
   - `deletion_allowed is false`;
   - `knowledge_source_count` reflects the exact count when using a knowledge source.
6. Attempt assistant deletion and assert `409 Conflict`.
7. Remove the dependency.
8. Fetch detail and assert deletion becomes allowed again.
9. Delete the assistant successfully.

Use the real PostgreSQL repository and real FastAPI route.

Do not use an in-memory dependency stub for this test.

---

## 4. Make pagination total-count coverage exact

Refactor or add a PostgreSQL pagination test with a fully controlled filter.

Create a set of assistants that can be selected exactly using status and visibility, while ensuring unrelated fixtures cannot match the same filter where possible.

Required assertions:

- exact total is the number of matching test-created assistants;
- `limit` changes page length but not total;
- `offset` changes returned records but not total;
- equal `created_at` values are ordered by ID;
- a second page contains the expected next record;
- a filter with no matching test-created records returns the expected controlled result.

If existing seeded data can match every available status/visibility combination, use an isolated test database or derive the expected baseline count before inserting test data:

1. record baseline count;
2. insert N matching assistants;
3. assert new total is baseline + N;
4. remove inserted assistants;
5. verify cleanup.

Do not rely on `total >= len(page)` as the primary correctness assertion.

---

## 5. Strengthen knowledge-source state preservation

Before changing assistant lifecycle, capture:

- assistant ID;
- source ID;
- document ID;
- retrieval state;
- ingestion status;
- active ingestion job ID where applicable;
- source enabled/disabled state;
- ownership fields.

After status and visibility changes, verify these values remain unchanged except where explicitly changed by the test itself.

Assistant lifecycle changes must not:

- start ingestion;
- cancel ingestion;
- replace the document;
- reset retrieval state;
- move the source;
- delete the source;
- create a duplicate source.

---

## 6. Validation requirements

Run the tests against a real isolated PostgreSQL database.

Set PostgreSQL-required test flags so database tests fail rather than skip.

At minimum:

```bash
cd apps/backend

../../venv/bin/ruff check .
../../venv/bin/ruff format --check .
../../venv/bin/mypy .
```

Run targeted assistant tests:

```bash
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest \
  tests/test_assistant_admin_api.py \
  tests/test_assistant_admin_api_postgres_integration.py \
  tests/test_assistant_admin_observability.py \
  tests/test_assistant_admin_repository_postgres_integration.py \
  tests/test_assistant_admin_service.py \
  tests/test_assistant_repository.py \
  -q
```

Run public-chat and knowledge-source regressions:

```bash
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
DATABASE_URL="<isolated-postgresql-test-database>" \
../../venv/bin/python -m pytest \
  tests/test_public_chat.py \
  tests/test_knowledge_source_api_postgres_integration.py \
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

Use actual repository commands if the paths differ.

---

## Acceptance criteria

- [ ] Re-ingestion succeeds for an inactive assistant.
- [ ] Re-ingestion succeeds for a private assistant.
- [ ] Retrieval can be disabled and re-enabled for inactive/private assistants.
- [ ] Re-ingestion preserves retrieval state.
- [ ] Re-ingestion remains correctly assistant-scoped.
- [ ] Cross-assistant source detail access remains blocked.
- [ ] Cross-assistant retrieval-state updates remain blocked.
- [ ] Cross-assistant re-ingestion remains blocked.
- [ ] Lifecycle changes do not weaken assistant isolation.
- [ ] PostgreSQL-backed assistant detail reports deletion allowed with no dependencies.
- [ ] PostgreSQL-backed assistant detail reports deletion blocked with a dependency.
- [ ] Knowledge-source count is accurate through the real API.
- [ ] Removing the final dependency makes deletion available again.
- [ ] Pagination total is tested exactly.
- [ ] Pagination total is independent of limit and offset.
- [ ] Equal-timestamp ID ordering remains deterministic.
- [ ] Ruff passes.
- [ ] Formatting check passes.
- [ ] Mypy passes.
- [ ] Targeted PostgreSQL tests pass without required skips.
- [ ] Public-chat regressions pass.
- [ ] Knowledge-source regressions pass.
- [ ] Full backend suite passes.
- [ ] Validation results include exact pass, fail and skip counts.
- [ ] No frontend files are changed.
- [ ] No unrelated refactor is introduced.

---

## Completion report

Report:

- exact files changed;
- exact commands run;
- exact pass, fail and skip counts;
- PostgreSQL version and database used;
- re-ingestion results for inactive and private assistants;
- retrieval disable/re-enable results;
- cross-assistant isolation results;
- dependency-aware detail results;
- exact pagination baseline and totals;
- any test that could not run;
- any remaining deviation from PR 11F.

Do not commit, push, merge or create another pull request.
