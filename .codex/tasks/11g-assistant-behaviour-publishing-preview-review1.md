PR 11G Follow-up — Complete Behaviour Publishing Integrity & Contract Gaps

Repository state

Expected branch:

feature/11g-assistant-behaviour-publishing-preview

Base branch:

main

Pull request:

#70 — Assistant Behaviour, Publishing & Preview API

Worktree:

Use the existing backend worktree containing PR #70.

This work must be completed on the existing PR #70 branch.

Do not create a new branch.

Do not create a second pull request.

Before making changes:

- confirm the current branch is feature/11g-assistant-behaviour-publishing-preview;
- confirm its HEAD contains the existing PR #70 implementation;
- inspect the complete diff against main;
- preserve the current behaviour revision model, admin API, preview flow, public-chat integration and prompt hierarchy;
- inspect current GitHub checks;
- do not broaden PR 11G beyond the corrective requirements below.

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/11g-assistant-behaviour-publishing-preview.md
- apps/backend/assistant/domain/assistant_behaviour.py
- apps/backend/assistant/domain/assistant_behaviour_repository.py
- apps/backend/assistant/application/assistant_behaviour_service.py
- apps/backend/assistant/application/public_chat.py
- apps/backend/assistant/application/prompt_builder.py
- apps/backend/assistant/api/assistant_behaviour.py
- apps/backend/assistant/infrastructure/repositories/assistant.py
- apps/backend/assistant/infrastructure/repositories/assistant_behaviour.py
- apps/backend/infrastructure/database/migrations/assistant_behaviour.py
- apps/backend/tests/test_assistant_behaviour_postgres.py
- apps/backend/tests/test_assistant_behaviour_api.py
- apps/backend/tests/test_assistant_preview_api.py
- apps/backend/tests/test_migrations.py
- apps/backend/tests/test_public_chat.py

⸻

Objective

Complete the missing correctness and verification requirements from the PR 11G specification without replacing the existing implementation.

The current PR already correctly establishes:

- Assistant-owned immutable behaviour revisions;
- separate draft and published revisions;
- optimistic concurrency;
- exact-revision publishing;
- authenticated administrator preview;
- public-chat use of published behaviour;
- preview use of saved draft behaviour;
- platform-controlled prompt hierarchy;
- Assistant-scoped retrieval;
- transactional Assistant behaviour creation;
- Assistant-owned behaviour deletion cascade.

Preserve those behaviours.

This follow-up must complete:

1. real PostgreSQL concurrency verification;
2. real PostgreSQL rollback verification;
3. representative pre-11G migration-upgrade verification;
4. Redmoor behaviour compatibility verification;
5. correct immutable revision timestamp semantics;
6. complete preview OpenAPI error documentation;
7. any directly related regression coverage required to prove the fixes.

No frontend changes are expected.

⸻

Required implementation

1. Fix draft revision timestamp semantics

The current API maps:

draft.updated_at = state.updated_at

This is incorrect because state.updated_at changes when publication state changes.

Publishing an immutable draft therefore causes the API-visible draft updated_at timestamp to change even though the revision itself has not changed.

Correct this.

Required semantics

A behaviour revision is immutable.

Its revision metadata must therefore remain stable after creation.

The API must not report publication-state mutation time as revision update time.

Choose one of the following approaches:

Preferred

Expose only immutable revision timestamps:

draft.created_at

Remove draft.updated_at if the revision model does not actually have an independently meaningful update timestamp.

Acceptable alternative

If the API contract genuinely requires updated_at, add a revision-owned timestamp with stable semantics.

For an immutable revision:

created_at == updated_at

unless the domain is redesigned to permit mutable drafts, which is not the current architecture and must not be introduced in this follow-up.

Required tests

Prove:

1. Save draft revision 2.
2. Record draft timestamp metadata.
3. Publish revision 2.
4. Fetch behaviour again.
5. Draft revision number and revision timestamp metadata remain unchanged.
6. Publication timestamp/state changes independently.

Do not derive revision timestamps from assistant_behaviour_states.updated_at.

⸻

2. Add real PostgreSQL concurrent draft-save verification

The original specification requires proof that stale concurrent writes cannot overwrite each other.

Existing sequential stale-token tests are useful but insufficient.

Add a real PostgreSQL concurrency test using two independent database connections/transactions.

Scenario

Initial state:

draft revision = 1
version = 1

Two writers A and B both observe concurrency token 1.

Writer A attempts to save draft A.

Writer B attempts to save draft B concurrently.

Required outcome:

exactly one succeeds
exactly one receives AssistantBehaviourUpdateConflict

Final state must contain only the successful draft.

Required assertions:

- no duplicate revision number;
- no lost update;
- no partially inserted revision;
- state version advances exactly as expected;
- published revision remains unchanged;
- losing transaction cannot overwrite winning state.

Do not simulate concurrency only by making sequential calls with an old token.

Use actual separate connections and transaction coordination.

A threading.Barrier, events, or equivalent deterministic coordination is acceptable.

Keep the test deterministic.

⸻

3. Add real PostgreSQL concurrent publish verification

Add PostgreSQL verification for publishing races.

Scenario A — same draft

Given:

draft revision = 2
published revision = 1

Two administrators attempt to publish revision 2 concurrently.

Required outcome:

- publication is idempotent in effect;
- final published revision is 2;
- no duplicate revision is created;
- publication state remains valid;
- at most one state-version mutation occurs if implementation semantics permit the second request to observe already-published state.

Document and assert the exact chosen behavior.

Scenario B — superseded draft

Coordinate this sequence:

A observes draft revision 2
B saves draft revision 3
A attempts to publish revision 2

Required:

A receives AssistantBehaviourPublishConflict

The server must never silently publish revision 3 on A’s behalf.

Final state:

draft = 3
published remains previous published revision

until an explicit valid publish of revision 3 occurs.

⸻

4. Verify rollback after draft revision insertion

The specification requires transactional integrity, not just successful-path tests.

Add an integration test that forces a failure after a new revision row is inserted but before the state pointer is successfully committed.

The exact injection method may follow existing repository test patterns.

Possible approaches:

- instrument a test-only connection/cursor wrapper;
- temporarily create a PostgreSQL trigger that raises on the state update;
- use an existing repository fault-injection mechanism if available.

Do not modify production behavior solely to make the test easy.

Required state before

draft = revision 1
published = revision 1

Attempt save revision 2, then force failure.

Required state after rollback

draft = revision 1
published = revision 1
version unchanged
revision 2 does not exist

There must be no orphan immutable revision from the failed transaction.

⸻

5. Verify rollback during publication

Force a publication failure inside the database transaction.

Before:

draft = 2
published = 1

Attempt publication of revision 2 and force an exception before commit.

After:

draft = 2
published = 1
published_at unchanged
version unchanged

No partially committed publication metadata may remain.

⸻

6. Verify transactional Assistant creation failure

PostgresAssistantRepository.create() now creates:

1. Assistant row;
2. default behaviour revision;
3. behaviour state.

The specification requires this to behave transactionally.

Add an integration test that causes behaviour initialization to fail after the Assistant insert.

Required outcome:

- the Assistant row is rolled back;
- no behaviour revision exists;
- no behaviour state exists;
- retrying creation after removing the injected failure can succeed cleanly.

Do not accept:

Assistant exists
behaviour absent

as a recoverable steady state.

⸻

7. Add representative pre-11G database migration test

The current migration test only inspects generated SQL through MagicMock.

Retain lightweight SQL-shape tests if useful, but add a real PostgreSQL upgrade test.

Construct a representative database state equivalent to immediately before PR 11G.

At minimum:

assistants table exists
Redmoor Assistant exists
another Assistant exists
no assistant_behaviour_revisions table
no assistant_behaviour_states table

Run the 11G migration.

Verify:

- behaviour revision table exists;
- behaviour state table exists;
- every existing Assistant gets revision 1;
- revision 1 is the current draft;
- revision 1 is published;
- published_at is populated consistently;
- version begins correctly;
- foreign keys work;
- cross-Assistant pointers are rejected;
- revision updates are rejected by immutability enforcement.

Do not rely exclusively on init_db() from an already fully migrated schema for this test.

The test must specifically demonstrate upgrade behavior from the pre-11G state.

⸻

8. Verify Redmoor effective public behaviour compatibility

The migration seeds Assistant-specific instructions, while platform grounding remains in PUBLIC_CHAT_SYSTEM_PROMPT.

The specification requires the existing Redmoor public Assistant to remain functionally compatible after migration.

Add an integration/regression test proving this explicitly.

Required verification

Start from a pre-11G Redmoor Assistant.

Apply the behaviour migration.

Resolve public chat for Redmoor.

Verify the final provider system prompt still includes the existing platform-controlled rules covering:

- grounded answers;
- retrieved knowledge as untrusted;
- conversation history as untrusted;
- current user input as untrusted;
- prohibition on following embedded instructions;
- prohibition on revealing hidden prompt/configuration;
- unsupported claims must not be invented;
- visible citations remain disabled according to the existing public contract.

Also verify:

- Redmoor has a valid published revision;
- public chat resolves that published revision;
- public chat still succeeds after migration.

Do not compare only one arbitrary string constant.

Assert the behavioral invariants that matter.

⸻

9. Verify immutable revision enforcement in PostgreSQL

Strengthen direct database coverage.

Prove that existing behaviour revisions cannot be updated.

Example:

UPDATE assistant_behaviour_revisions
SET instructions = ...
WHERE assistant_id = ... AND revision = ...

must fail.

After failure, original content remains unchanged.

Also verify that deletion or mutation of revisions referenced by current state cannot break referential integrity.

Do not weaken immutability to make administrative editing simpler.

Editing must continue to create new revisions.

⸻

10. Strengthen suggested-question database constraints

Review the migration and domain validation parity.

The database currently validates:

- JSON array;
- maximum count;
- string entries;
- non-empty strings;
- length;
- newline/carriage-return constraints.

Ensure database constraints are compatible with domain restrictions on unsafe control characters.

The database does not need to reproduce every Unicode-category rule if doing so would require brittle custom logic, but malformed persisted state must not be possible through normal repository paths.

Add tests proving repository/domain validation prevents unsafe values before SQL execution.

If direct SQL can bypass important invariants that materially affect API/runtime safety, add a database constraint or trigger check.

Do not introduce an elaborate Unicode-validation SQL framework unless necessary.

⸻

11. Complete preview OpenAPI error responses

preview_chat() can return:

504 request_timed_out

but the route’s documented ERROR_RESPONSES currently omits 504.

Correct the API documentation.

The Preview endpoint should document all supported non-SSE HTTP failures, including as applicable:

- 401
- 403
- 404
- 409
- 422
- 504

If preparation can safely produce another deterministic HTTP error, document it as well.

Do not document streamed generation failures as HTTP failures if they occur after the SSE stream begins.

Add an OpenAPI/schema regression assertion if the repository has an established pattern for API documentation testing.

⸻

12. Complete preview failure coverage

Extend test_assistant_preview_api.py.

Add coverage for:

- Assistant not found;
- behaviour unavailable;
- excessive input/token budget;
- preparation timeout;
- provider generation failure emitted as safe SSE error;
- provider timeout emitted as safe SSE error if supported;
- history validation failure;
- prompt/instruction contents absent from error responses;
- request does not mutate behaviour state after failure;
- preview works for inactive/private Assistant;
- published revision remains unchanged after preview.

Do not expose raw provider exceptions.

⸻

13. Complete public-chat snapshot consistency coverage

The specification requires each chat request to use one internally consistent behaviour snapshot.

Add a deterministic test proving:

1. public request resolves published revision 2;
2. publication changes to revision 3 after request preparation but before event generation;
3. the already-prepared request continues using revision 2;
4. the next public request uses revision 3.

Do not repeatedly resolve behaviour during a prepared request.

Add the equivalent preview test where practical:

1. preview resolves draft revision 4;
2. draft revision 5 is saved after preparation;
3. prepared preview continues using revision 4;
4. next preview uses revision 5.

⸻

14. Preserve current prompt hierarchy

Do not weaken the existing prompt composition while correcting tests.

Keep:

platform-controlled rules >
Assistant-specific administrator instructions >
untrusted retrieval/history/current user message

Preserve JSON escaping/delimiter neutralization.

Add or retain tests proving administrator instructions containing apparent closing tags cannot escape the Assistant instruction section.

Do not move administrator instructions ahead of platform rules.

⸻

15. Preserve insufficient-knowledge behavior

Public and Preview flows must continue bypassing generation when no acceptable retrieval chunks exist.

Administrator instructions must not be able to force speculative generation without evidence.

Add a Preview regression test for no retrieved knowledge if missing.

Required:

- deterministic insufficient-knowledge response;
- no provider call;
- no draft/publication mutation;
- safe completion event.

⸻

16. Verification evidence

The GitHub Actions workflow currently passes, but passing CI alone does not prove the missing PR 11G database scenarios.

Update CI configuration only if necessary to ensure the newly required PostgreSQL tests cannot silently skip.

The existing behavior where PostgreSQL tests fail rather than skip in CI should be preserved.

Ensure the new concurrency/rollback/migration tests run in CI.

Do not claim scenarios were verified if they remain skipped locally and absent from CI.

⸻

Acceptance criteria

- Draft revision timestamps no longer change merely because the revision is published.
- Revision metadata is sourced from revision-owned state, not mutable publication-state timestamps.
- Two concurrent draft saves cannot both overwrite the same version.
- Exactly one concurrent conflicting draft save wins.
- Losing concurrent draft save receives a deterministic conflict.
- Concurrent publishing is safe and deterministic.
- A stale administrator cannot accidentally publish a newer draft.
- Failed draft save after revision insertion rolls back the revision row.
- Failed draft save leaves state version/pointers unchanged.
- Failed publication leaves published pointer/timestamp/version unchanged.
- Failed Assistant creation leaves no Assistant or behaviour orphan rows.
- A real pre-11G PostgreSQL database can be upgraded successfully.
- Existing Assistants receive deterministic revision 1 during migration.
- Redmoor receives valid migrated draft/published state.
- Redmoor public chat retains existing grounding/security behavior after migration.
- Behaviour revisions are immutable at the PostgreSQL level.
- Cross-Assistant revision pointers remain impossible.
- Suggested-question persisted state remains valid and safe.
- Preview OpenAPI documents 504 timeout responses.
- Preview failure tests cover not-found, unavailable, validation, timeout and safe generation failure.
- Preview errors do not expose prompt/provider contents.
- Preview failures do not mutate behaviour/publication state.
- Prepared public requests retain their originally resolved published revision.
- Prepared Preview requests retain their originally resolved draft revision.
- Future requests resolve newer authoritative revisions correctly.
- Insufficient-knowledge Preview does not call the provider.
- Platform prompt protections remain immutable.
- Existing public SSE contract remains unchanged.
- Existing Assistant lifecycle behavior remains unchanged.
- Existing knowledge/retrieval behavior remains unchanged.
- Existing PR 11G unit/API tests remain passing.
- New PostgreSQL integrity tests run in CI without skips.
- Full backend test suite passes.
- Ruff passes.
- Ruff formatting check passes.
- mypy passes.
- git diff --check passes.

⸻

Tests to add or update

Primary expected files:

apps/backend/tests/test_assistant_behaviour_postgres.py
apps/backend/tests/test_assistant_behaviour_api.py
apps/backend/tests/test_assistant_preview_api.py
apps/backend/tests/test_migrations.py
apps/backend/tests/test_public_chat.py
apps/backend/tests/test_prompt_builder.py

Add another focused PostgreSQL migration/integrity test file only if it materially improves clarity.

Do not split tests into unnecessary micro-files.

⸻

Verification commands

Run from the repository root.

git status -sb
cd apps/backend

# Focused behaviour domain/API

venv/bin/python -m pytest -q \
 tests/test_assistant_behaviour.py \
 tests/test_assistant_behaviour_repository.py \
 tests/test_assistant_behaviour_api.py \
 tests/test_assistant_preview_api.py \
 tests/test_prompt_builder.py \
 tests/test_public_chat.py

# Required real PostgreSQL verification

ASSISTANT_BEHAVIOUR_POSTGRES_REQUIRED=true \
venv/bin/python -m pytest -q \
 tests/test_assistant_behaviour_postgres.py \
 tests/test_migrations.py

# Full backend verification

venv/bin/python -m pytest -q
venv/bin/python -m ruff check .
venv/bin/python -m ruff format --check .
venv/bin/python -m mypy .
cd ../..
git diff --check
git status -sb

If real migration-upgrade tests are moved into another existing PostgreSQL test file, include that file in the required command.

Also inspect the GitHub Actions run after pushing and confirm the new PostgreSQL scenarios are actually executed.

⸻

Manual database verification

Where a disposable PostgreSQL database is available, verify:

1. Start with the pre-11G Assistant schema.
2. Seed Redmoor plus one additional Assistant.
3. Run the 11G migration.
4. Inspect both behaviour tables.
5. Confirm every Assistant has revision 1 and valid publication state.
6. Start two concurrent draft updates from the same concurrency token.
7. Confirm one wins and one conflicts.
8. Save draft revision 2.
9. Publish revision 2.
10. Confirm draft revision metadata does not change because of publication.
11. Save revision 3.
12. Confirm public chat remains on revision 2.
13. Confirm Preview uses revision 3.
14. Publish revision 3.
15. Confirm subsequent public chat uses revision 3.
16. Force a save transaction failure and verify no orphan revision.
17. Force a publish transaction failure and verify published state remains unchanged.
18. Confirm prompt/preview contents do not appear in logs.

Do not claim manual verification unless actually performed.

⸻

Completion rule

The follow-up is complete only when PR #70 proves, with real PostgreSQL execution, that:

revision creation
publication
concurrency
migration
rollback

remain correct under both normal and failure conditions.

The final PR must preserve the existing architecture:

saved draft
↓
Preview
published revision
↓
Public chat

while guaranteeing that immutable revision metadata remains truthful, stale writers cannot overwrite newer state, failed transactions leave no partial data, and existing Redmoor behavior survives migration without regression.
