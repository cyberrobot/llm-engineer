# PR 13C Follow-up 2 — Complete Accessibility, Regression Evidence and PR Verification

## Repository state

Expected branch:

`feature/13c-assistant-knowledge-retrieval-configuration`

Base branch:

`main`

Pull request:

`#66 — Add assistant knowledge retrieval configuration`

Expected reviewed head at the start of this follow-up:

`ecd8819e08bf63022d041551b761806693fa2544`

Continue on the existing PR #66 branch. Do **not** create another branch or pull request. If the
remote head has moved, inspect the new diff and preserve any newer in-scope corrections before
editing.

### Governing specifications

- `.codex/tasks/13c-assistant-knowledge-retrieval-configuration.md`
- `.codex/tasks/13c-assistant-knowledge-retrieval-configuration-review1.md`

This document addresses only the requirements still incomplete after the second review. Requirements
already satisfied by PR #66 remain authoritative and must not regress.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- both governing specifications above
- `apps/admin/README.md`
- `apps/admin/package.json`
- `apps/admin/src/App.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/api/adminApi.ts`
- `apps/admin/src/api/adminApi.test.ts`
- `apps/admin/src/features/knowledge-sources/KnowledgeSources.tsx`
- `apps/admin/src/features/knowledge-sources/KnowledgeSources.stories.tsx`

Before implementation:

1. Confirm the branch and PR head.
2. Inspect the full diff against `origin/main` and the current working-tree status.
3. Inspect PR #66 checks and unresolved review threads.
4. Add behavior-focused regression tests and observe the expected failures before production fixes
   where practical.
5. Preserve the existing backend contract, idempotency lifecycle, list/detail mutations, safe error
   mapping, deterministic stories and documentation.

## Objective

Resolve the remaining approval blockers identified while reviewing PR #66 against PR 13C:

1. creation-result status announcements are rendered but not reliably focused after detail loading;
2. the source-list detail action has an ambiguous accessible name;
3. mandatory API-boundary and rendered-workflow regression cases remain absent;
4. the PR description inaccurately says verification was not run.

No backend, database, dependency, RAG UI or public Assistant widget changes are expected.

## Required implementation

### 1. Focus creation-result announcements after authoritative detail loads

`KnowledgeSourceDetailPage` initializes its creation notice from safe React Router navigation state.
The current focus effect runs while the page still returns `Loading knowledge source…`; the notice
element is not mounted at that point. Loading the Assistant and source does not change the notice, so
the effect does not run again and the queued/reused announcement may never receive focus.

Required behavior:

- Continue to validate that navigation state contains the current route source identifier and only a
  stable `queued` or `reused` outcome.
- Continue to fetch authoritative source detail before presenting the completed detail view.
- Once the detail view and creation-result status are mounted, move focus to that status exactly once.
- Do not steal focus for direct navigation, refresh, ordinary detail loading, or later source refresh
  when no valid creation result exists.
- Clear consumed navigation state with replacement navigation so refresh does not recreate the
  announcement.
- Do not place source content, URLs or idempotency keys in navigation state.
- Preserve focus restoration to the initiating action after enable/disable and re-ingestion success.
- Avoid timers that make the behavior race-prone. Prefer a lifecycle condition based on the mounted
  source/Assistant and the validated notice.

Add rendered tests for both queued and reused creation outcomes. Each test must verify:

- the canonical detail is fetched and rendered;
- the correct status text is present;
- the status receives focus after loading;
- the URL contains no operation outcome, source content or idempotency key;
- a direct visit or refresh does not fabricate or repeat the announcement.

### 2. Give the list detail action an unambiguous accessible name

Every populated source card must expose a view-details action whose accessible name identifies both
the action and source.

Required behavior:

- Use an accessible name such as `View details for Policy guide`.
- Keep the source name visible as the card heading.
- Preserve the canonical Assistant-scoped detail URL.
- Do not add duplicate links or change the names of enable/disable, re-ingest and delete actions.
- Keep the card understandable without relying on iconography or visual position.

Add a rendered assertion for the exact view-details accessible name and destination.

### 3. Complete API-boundary regression coverage

Extend `apps/admin/src/api/adminApi.test.ts` without duplicating existing cases.

Required additional cases:

#### Cancellation

- Verify the exact `AbortSignal` is forwarded by `listKnowledgeSources()`.
- Verify the exact `AbortSignal` is forwarded by `getKnowledgeSource()`.
- Confirm abort rejection remains an `AbortError`, not a mapped administrator error.

#### Knowledge failure mapping

Exercise the knowledge boundary for:

- `401` → `unauthenticated`;
- `403` → `forbidden`;
- `404` → safe `not_found` with only the contractual code;
- `422` → `invalid_request`;
- `409 idempotency_key_conflict` → safe conflict code;
- `409 active_ingestion` → safe conflict code;
- `5xx` → `server`;
- invalid successful JSON or malformed success → `invalid_response`.

For every mapping, assert raw backend messages, HTML, provider payloads and response bodies are not
retained in the public error message.

#### Enum and operation boundaries

- Verify both source types and both retrieval states are accepted through observable returned values.
- Verify a later independent re-ingestion operation can receive a different caller-owned key while
  an identical explicit retry preserves its supplied key.
- Retain the existing ingestion-status, ingestion-step, URL, timestamp, pagination and HTTP-status
  coverage.

Tests must verify returned values or safe errors plus the exact request path, method, credentials,
signal, headers and body where relevant. Mock-call-only assertions are insufficient.

### 4. Complete rendered knowledge-workflow regression coverage

Extend `apps/admin/src/App.test.tsx` through the public route and API boundary. Reuse existing fixed
fixtures and helpers rather than introducing a feature-hook mock layer.

#### Routing, loading and pagination

- Assistant not-found and source/cross-Assistant not-found use the required safe presentations.
- Knowledge list loading, empty, retryable failure, manual refresh and populated states remain usable.
- Navigate to a later source page, delete its final item, receive an authoritative lower total, and
  verify the UI corrects to the valid preceding offset.
- Verify the Assistant source count is fetched again after successful deletion.
- Verify the stable post-deletion focus target after page correction.

#### Creation validation and state

- Required and maximum-length name behavior.
- Required, non-whitespace and maximum-length direct text behavior.
- Reject URL schemes other than HTTP(S), embedded credentials and fragments before mutation.
- Source-type switching preserves local values but submits only the selected discriminated payload.
- Pending creation prevents duplicate submission.
- Dirty knowledge forms warn before route navigation.
- Validation, network and idempotency-conflict failures retain field values and focus the error
  summary.
- Queued and reused outcomes satisfy the focus requirements in section 1.
- Assert source content and idempotency keys do not enter route URLs or browser storage.

#### Retrieval and mutation ordering

- Enable and disable confirmations send exact retrieval-state payloads.
- A failed retrieval mutation retains the last confirmed state.
- A stale or late response cannot regress a newer confirmed state; if the modal design makes
  concurrent mutations impossible, assert that conflicting controls cannot initiate another request.
- Pending re-ingestion disables confirmation controls and prevents duplicate submission.
- New-job and active-job-reuse outcomes remain distinct and accessible.
- Idempotency conflict gives refresh guidance and does not silently retry.

#### Session, deletion and focus

- A protected knowledge mutation returning `401` invalidates the session and returns to login.
- The equivalent `403` preserves the authenticated shell and presents a safe error.
- Active-ingestion conflict retains the source.
- Already-missing deletion reconciles authoritative collection state safely.
- Dialog focus returns after Cancel, Escape, successful enable/disable, successful re-ingestion and
  dismissal after recoverable failure.
- Successful deletion focuses a stable remaining control after the refreshed list mounts.

Use semantic assertions for visible state, focus, route, persisted collection/count and exact API
input. Do not weaken existing PR 13A/13B coverage.

### 5. Preserve deterministic Storybook behavior

No new story is required solely to fix the focus lifecycle if the existing queued/reused creation
stories remain accurate. Update story play assertions where practical to verify the status is mounted
after authoritative detail loading.

All stories must continue to:

- use fixed fictional data;
- use only fake `AdminApi` implementations;
- avoid live cookies, authentication and network requests;
- avoid current time and shared mutable state;
- render through routes that supply the required Assistant/source parameters.

### 6. Update PR verification evidence

After all implementation and verification work is complete, update PR #66's description.

Required content:

- concise summary of the PR 13C functionality and both follow-up corrections;
- exact local commands actually run and their final results;
- current GitHub Actions check results;
- explicit statement that live backend/worker/manual scenarios were not run if they were not
  observed;
- no remaining `Not run (not requested)` statement after commands have run.

Do not claim manual scenarios, worker ingestion, PostgreSQL integration or browser inspection unless
they were actually completed. Updating the PR description is an external write and must occur only
after verification succeeds.

## Out of scope

- Backend endpoint, schema, worker or persistence changes.
- New knowledge-source types, file upload or crawling.
- Source editing or ingestion cancellation.
- Similarity, top-K, reranking, chunking, embedding or model controls.
- A general mutation/data-grid framework.
- RAG UI or published Assistant widget changes.
- Refactoring unrelated PR 13A/13B code.

## Acceptance criteria

- [ ] Queued and reused creation announcements receive focus after authoritative detail mounts.
- [ ] Direct navigation and refresh do not fabricate or repeat creation announcements.
- [ ] Creation navigation state remains limited to source identifier and stable outcome enum.
- [ ] List view-details actions have unambiguous source-specific accessible names.
- [ ] Knowledge read cancellation and all contractual failure mappings have API-boundary coverage.
- [ ] Both source/retrieval enums and independent re-ingestion keys have observable API coverage.
- [ ] Final-page deletion correction and Assistant-count refresh have rendered coverage.
- [ ] Creation validation, duplicate prevention, dirty navigation and safe failure retention have
  rendered coverage.
- [ ] Retrieval failure/concurrency and re-ingestion pending/conflict behavior have rendered
  coverage.
- [ ] Knowledge mutation `401` and `403` behavior has rendered coverage.
- [ ] Cancel, Escape, mutation success/failure and deletion focus paths have rendered coverage.
- [ ] Sensitive content and idempotency keys remain absent from storage, URLs and unsafe errors.
- [ ] Existing deterministic stories still build and make no network requests.
- [ ] Existing authentication and Assistant management tests remain passing.
- [ ] No backend, dependency, migration, RAG UI or public widget behavior changes.
- [ ] Admin test, type-check, lint, production build and Storybook build pass.
- [ ] Backend knowledge-source contract tests pass without production backend changes.
- [ ] Current GitHub Actions required checks pass for the final pushed head.
- [ ] PR #66 accurately reports verification and manual-test limitations.
- [ ] `git diff --check` passes and the working tree contains only intended changes.

## Verification commands

Run from the repository root:

```bash
git status -sb

npm test --workspace @ai-discovery-assistant/admin -- src/api/adminApi.test.ts
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx

npm run test:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run lint:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

cd apps/backend
venv/bin/python -m pytest -q tests/test_knowledge_source_api.py
cd ../..

git diff --check
git status -sb
```

After pushing the final commit, inspect PR #66 and verify all required checks apply to that exact head
SHA. Do not treat checks from an earlier commit as final evidence.

Where a local browser, administrator session, backend and worker are available, manually verify the
focus and keyboard paths. If those services are unavailable, report the scenarios as not run rather
than blocking safe automated corrections.

## Completion report

Report:

1. branch, final head and files changed;
2. initial expected regression failures observed;
3. creation-announcement and list-action accessibility corrections;
4. API and rendered regression cases added;
5. confirmation that backend contracts, dependencies and other applications were unchanged;
6. exact commands and final results;
7. final GitHub Actions status and PR description update;
8. manual scenarios actually completed versus not run;
9. remaining deviations or risks.
