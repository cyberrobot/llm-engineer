PR 11G Follow-up 2 — Fix Concurrent Behaviour State Reads

Repository state

Expected branch:

feature/11g-assistant-behaviour-publishing-preview

Pull request:

#70 — Assistant Behaviour, Publishing & Preview API

Base branch:

main

This work must be implemented on the existing PR #70 branch.

Do not create a new branch.

Do not create a second PR.

Do not revert or weaken the concurrency tests added by the previous follow-up.

Before changing code:

- confirm the branch is feature/11g-assistant-behaviour-publishing-preview;
- confirm PR #70 head contains the existing PR 11G implementation and follow-up integrity tests;
- inspect the current failed CI run;
- reproduce the two failing PostgreSQL concurrency tests;
- preserve all existing PR 11G API contracts and domain semantics.

Read first

- .codex/tasks/11g-assistant-behaviour-publishing-preview.md
- .codex/tasks/11g-assistant-behaviour-publishing-preview-review1.md
- apps/backend/assistant/domain/assistant_behaviour.py
- apps/backend/assistant/domain/assistant_behaviour_repository.py
- apps/backend/assistant/infrastructure/repositories/assistant_behaviour.py
- apps/backend/tests/test_assistant_behaviour_postgres.py
- apps/backend/tests/test_assistant_behaviour_repository.py
- apps/backend/tests/test_assistant_behaviour_api.py
- apps/backend/tests/test_public_chat.py
- apps/backend/tests/test_assistant_preview_api.py
- apps/backend/infrastructure/database/connection.py

⸻

Objective

Fix the remaining PostgreSQL concurrency defect in PR 11G.

The current implementation correctly provides:

- immutable Assistant behaviour revisions;
- separate draft and published revisions;
- optimistic concurrency tokens;
- exact-draft publication;
- draft Preview;
- published public chat;
- transactional behaviour mutations;
- database ownership constraints;
- rollback tests;
- migration tests;
- snapshot consistency tests.

However, the PostgreSQL repository currently resolves the mutable behaviour state row and its referenced revision rows in a single joined query while attempting to lock only the state row.

Under concurrent transactions this can produce an internally inconsistent read.

The current CI failures demonstrate the bug.

This follow-up must make behaviour state resolution concurrency-safe without changing external semantics.

⸻

Current defect

PostgresAssistantBehaviourRepository.save_draft() and publish() call:

state = self.\_read_state(cursor, assistant_id, lock=True)

The current \_read_state() performs one query resembling:

SELECT
state columns,
draft revision columns,
published revision columns
FROM assistant_behaviour_states s
JOIN assistant_behaviour_revisions d
ON ...
LEFT JOIN assistant_behaviour_revisions p
ON ...
WHERE s.assistant_id = ?
FOR UPDATE OF s

This is not safe for this use case under PostgreSQL READ COMMITTED.

A transaction may begin the statement, wait for another transaction’s lock on assistant_behaviour_states, then continue after the state row has changed.

The locked state row may now contain a newer:

draft_revision
or
published_revision

while joined revision rows were derived from the earlier statement snapshot.

This has already caused:

AssistantBehaviourNotFound

during concurrent draft saving and:

TypeError: 'NoneType' object is not iterable

during concurrent publication.

These are production correctness failures, not merely test-harness issues.

⸻

Required implementation

1. Separate locking from state hydration

Do not use a single joined SELECT ... FOR UPDATE OF s to both:

- acquire the mutable state-row lock;
- hydrate draft and published immutable revisions.

When a mutation requires locking, use two phases.

Phase 1 — lock authoritative state row

Execute a narrow query such as:

SELECT
assistant_id,
draft_revision,
published_revision,
published_at,
version,
updated_at
FROM assistant_behaviour_states
WHERE assistant_id = %s
FOR UPDATE

This statement must complete and acquire the row lock before revision rows are resolved.

Phase 2 — hydrate referenced revisions

After the lock is acquired, resolve:

- draft revision;
- published revision, if present;

using a new SQL statement executed in the same transaction.

Because this second statement begins after the lock wait has completed, it must see the committed revision relationships corresponding to the locked state row.

Do not release the state lock between these operations.

⸻

2. Preserve transaction boundaries

save_draft() must continue operating inside one database transaction:

open transaction
↓
lock behaviour state
↓
validate concurrency token
↓
insert immutable revision
↓
update draft pointer/version
↓
read authoritative resulting state
commit

publish() must remain:

open transaction
↓
lock behaviour state
↓
validate expected token + exact draft
↓
update published pointer/version
↓
read authoritative resulting state
commit

Do not split mutation operations across multiple connections.

Do not commit immediately after acquiring the lock.

⸻

3. Introduce explicit repository helpers

Refactor for clarity rather than embedding more conditionals into \_read_state().

A suitable shape is:

def \_read_state_row(
cursor,
assistant_id,
\*,
lock: bool,
) -> BehaviourStateRow:
...
def \_read_revision(
cursor,
assistant_id,
revision,
) -> AssistantBehaviourRevision:
...
def \_hydrate_state(
cursor,
state_row,
) -> AssistantBehaviourState:
...

or equivalent.

Another acceptable design:

def \_lock_state(...)
def \_read_state(...)

where mutations do:

self.\_lock_state(cursor, assistant_id)
state = self.\_read_state(cursor, assistant_id)

Prefer a typed internal representation for the state row if that improves readability.

Do not expose new concepts through the public repository protocol unless required.

⸻

4. Preserve missing-state semantics

The repository must continue distinguishing:

Missing Assistant

Raise:

AssistantNotFound

Existing Assistant without initialized behaviour

Raise:

AssistantBehaviourNotFound

Do not convert these into generic SQL exceptions.

If using a narrow lock query and it returns no row, check Assistant existence exactly once as needed.

Avoid unnecessary duplicate Assistant queries.

⸻

5. Do not tolerate inconsistent references silently

After acquiring the authoritative state row lock, a referenced draft revision must exist.

If:

draft_revision = N

but the matching revision row is absent, this indicates database corruption/invariant violation.

Do not silently fall back to revision 1.

Do not fabricate default behaviour.

Do not return partial state.

Use the existing domain/repository exception convention or raise a clear internal invariant exception that is never exposed raw through the API.

The same applies when published_revision is non-null but its revision row does not exist.

The database FKs should normally make these situations impossible.

⸻

6. Fix concurrent draft-save behaviour

Preserve the existing required test:

test_concurrent_draft_saves_from_same_token_have_exactly_one_winner

Expected behavior:

Two writers share the same original concurrency token.

Exactly one succeeds.

Exactly one receives:

AssistantBehaviourUpdateConflict

Final state:

draft revision = 2
version = 2
published revision = 1

Exactly two revision rows exist:

revision 1
revision 2

The losing transaction must not observe:

AssistantBehaviourNotFound
TypeError
ForeignKeyViolation
UniqueViolation

or another infrastructure exception.

⸻

7. Fix concurrent same-draft publication behaviour

Preserve:

test_concurrent_publish_of_same_draft_is_idempotent_with_one_version_mutation

Given:

draft = 2
published = 1
version = 2

Two callers concurrently publish revision 2 using the same valid observed token.

Required final state:

draft = 2
published = 2
version = 3

Both operations may return success if the existing idempotent contract is retained.

The second transaction, after acquiring the row lock, should detect:

draft == published == requested revision

and return current authoritative state without incrementing version again.

No duplicate revision may be created.

No partial published revision object may be constructed.

⸻

8. Preserve stale publication behavior

The following behavior must remain unchanged:

A observes draft 2
B saves draft 3
A publishes draft 2

A must receive:

AssistantBehaviourPublishConflict

Final state:

draft = 3
published = previous published revision

Do not relax the expected-token or exact-draft checks to solve concurrent same-revision publication.

⸻

9. Preserve idempotent publish ordering

Current semantics intentionally allow:

requested revision already equals draft and published

to return authoritative state even if the original request token is now stale because the same publication already succeeded.

Preserve this behavior unless the original PR 11G spec explicitly requires otherwise.

The check order should remain logically equivalent to:

if already_published_exact_requested_draft:
return current_state
if stale_token_or_wrong_draft:
raise AssistantBehaviourPublishConflict

This is what permits safe concurrent duplicate publication.

⸻

10. Keep immutable revisions unchanged

Do not alter the revision model.

Continue to enforce:

- revision rows are immutable;
- draft edits create a new revision;
- publication only moves the published pointer;
- publication never modifies revision timestamps/content;
- draft and published may reference the same immutable revision.

Do not convert the draft into a mutable row to simplify locking.

⸻

11. Preserve snapshot semantics for chat

This fix must not change public or Preview chat behavior.

Public chat:

resolve published revision during prepare
→ prepared request keeps that revision

Preview:

resolve draft revision during prepare
→ prepared request keeps that revision

Do not make chat streaming re-read behaviour state after preparation.

Existing snapshot consistency tests must remain passing.

⸻

12. Preserve API behavior

No external API contract changes are required.

Keep:

GET /admin/assistants/{id}/behaviour
PUT /admin/assistants/{id}/behaviour
POST /admin/assistants/{id}/behaviour/publish
POST /admin/assistants/{id}/preview/chat

Keep existing:

- response schemas;
- concurrency token semantics;
- 409 conflict codes;
- preview SSE contract;
- status/visibility separation.

Frontend 13D must not need another API adaptation because of this fix.

⸻

Tests

Required PostgreSQL tests

The following existing tests must pass unchanged in intent:

test_concurrent_draft_saves_from_same_token_have_exactly_one_winner
test_concurrent_publish_of_same_draft_is_idempotent_with_one_version_mutation
test_publish_rejects_draft_superseded_after_administrator_observed_it
test_failed_state_update_rolls_back_inserted_draft_revision
test_failed_publication_rolls_back_pointer_timestamp_and_version
test_failed_behaviour_initialization_rolls_back_assistant_and_retry_succeeds

Do not delete, skip, xfail, or weaken assertions in these tests merely to make CI green.

Adjust test mechanics only if they contain an independent defect, and document why.

⸻

Add focused regression coverage for state hydration

Add at least one lower-level PostgreSQL regression test proving state hydration after a lock wait uses the post-lock authoritative revision pointers.

A deterministic test may coordinate:

1. Transaction A locks behaviour state.
2. Transaction B begins a mutation and blocks waiting for the same row.
3. Transaction A changes the state pointer and commits.
4. Transaction B resumes.
5. Transaction B must hydrate the revision corresponding to the newly locked state row.

Assert that B never observes:

new pointer + old/null joined revision data

This test should target the exact bug that caused CI failure rather than relying solely on higher-level behavior tests.

⸻

Repository parity

Run in-memory repository tests to ensure PostgreSQL fixes do not alter public repository semantics.

PostgreSQL and in-memory behavior should agree on:

- unchanged save;
- successful save;
- stale save;
- successful publish;
- repeated same publish;
- stale/wrong-draft publish.

⸻

CI requirements

The latest CI currently fails in the main backend pytest step.

After the fix:

- full backend pytest must pass;
- the explicit required Assistant behaviour PostgreSQL step must execute rather than be skipped due to an earlier failure;
- it must pass with ASSISTANT_BEHAVIOUR_POSTGRES_REQUIRED=true.

Do not remove that required CI step.

Do not remove ASSISTANT_BEHAVIOUR_POSTGRES_REQUIRED=true.

⸻

Acceptance criteria

- Mutable state-row locking is separated from revision hydration.
- No joined FOR UPDATE OF s query is relied on to produce an authoritative post-wait state snapshot.
- save_draft() acquires the state lock before validating the concurrency token.
- publish() acquires the state lock before validating publication state.
- Revision rows are resolved only after authoritative state locking for mutations.
- Concurrent saves produce exactly one success and one domain conflict.
- Concurrent saves never produce AssistantBehaviourNotFound.
- Concurrent saves never produce revision UniqueViolation under the tested same-token race.
- Concurrent same-revision publishing is idempotent in effect.
- Concurrent publishing does not construct a partial published revision.
- Concurrent publishing never produces TypeError from null joined revision columns.
- Duplicate same-revision publication increments version at most once.
- Stale publication of a superseded draft still returns deterministic conflict.
- Draft/published ownership invariants remain enforced.
- Revision immutability remains enforced.
- Rollback tests remain passing.
- Migration tests remain passing.
- Redmoor migration compatibility remains passing.
- Public chat snapshot tests remain passing.
- Preview snapshot tests remain passing.
- API contracts remain unchanged.
- Full backend pytest suite passes.
- Required Assistant PostgreSQL CI step executes and passes.
- Ruff passes.
- Ruff formatting passes.
- mypy passes.
- git diff --check passes.

⸻

Verification commands

Run from repository root.

git status -sb
cd apps/backend
ASSISTANT_BEHAVIOUR_POSTGRES_REQUIRED=true \
venv/bin/python -m pytest -q \
 tests/test_assistant_behaviour_postgres.py
venv/bin/python -m pytest -q \
 tests/test_assistant_behaviour_repository.py \
 tests/test_assistant_behaviour_api.py \
 tests/test_assistant_preview_api.py \
 tests/test_public_chat.py \
 tests/test_migrations.py
venv/bin/python -m pytest -q
venv/bin/python -m ruff check .
venv/bin/python -m ruff format --check .
venv/bin/python -m mypy .
cd ../..
git diff --check
git status -sb

After pushing, inspect GitHub Actions.

Confirm:

Backend tests success
Required Assistant PostgreSQL tests success
Storybook tests success

Do not report completion while the PR check remains red.

⸻

Completion rule

The follow-up is complete only when PostgreSQL mutation reads obey this sequence:

lock authoritative behaviour state
↓
resolve referenced immutable revisions
↓
validate concurrency/publication preconditions
↓
perform mutation
↓
return internally consistent authoritative state

The fix must eliminate the current race without weakening optimistic concurrency, immutable revisions, exact-draft publishing, idempotent duplicate publication, or public/Preview behavior.
