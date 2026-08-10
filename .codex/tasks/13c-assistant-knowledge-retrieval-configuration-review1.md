# PR 13C Follow-up — Resolve Knowledge & Retrieval Review Findings

## Repository state

Expected branch:

`feature/13c-assistant-knowledge-retrieval-configuration`

Base branch:

`main`

Pull request:

`#66 — Add assistant knowledge retrieval configuration`

Worktree:

Use the existing frontend worktree containing PR #66.

This work must be completed on the existing PR #66 branch. Do **not** create a new branch or pull
request. Do not replace the implementation or broaden PR 13C beyond the corrective scope below.

Before changing code:

- confirm the current branch is `feature/13c-assistant-knowledge-retrieval-configuration`;
- confirm its head contains the existing PR #66 implementation;
- inspect the full diff against `main`;
- preserve correct Assistant-scoped routing, authentication, validation and source workflows;
- inspect current GitHub checks and unresolved review threads;
- write or update behavior-focused tests before each production correction where practical.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/13c-assistant-knowledge-retrieval-configuration.md`
- `apps/admin/README.md`
- `apps/admin/package.json`
- `apps/admin/src/App.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/api/adminApi.ts`
- `apps/admin/src/api/adminApi.test.ts`
- `apps/admin/src/features/knowledge-sources/KnowledgeSources.tsx`
- `apps/admin/src/features/knowledge-sources/KnowledgeSources.stories.tsx`
- `apps/admin/src/features/assistants/Assistants.tsx`
- `apps/admin/src/components/AdminShell.tsx`
- `apps/admin/src/styles.css`
- `apps/backend/assistant/api/knowledge_sources.py`
- `apps/backend/assistant/schemas/knowledge_source.py`
- `apps/backend/tests/test_knowledge_source_api.py`

---

## Objective

Resolve the blocking and partial requirements found during the review of PR #66 against PR 13C.

The existing PR correctly establishes the Assistant-scoped routes, typed backend boundary, source
creation, retrieval-state mutation, re-ingestion, deletion, runtime response validation, stories and
documentation. Preserve those behaviors.

This follow-up must complete:

- safe idempotent retries for creation and re-ingestion;
- visible queued/reused creation outcomes;
- required per-source actions from the knowledge list;
- complete operational detail;
- deterministic dialog focus restoration;
- the missing Storybook and regression-test matrix;
- truthful pull-request verification evidence.

No backend changes are expected. If the verified backend contract cannot support a requirement,
stop and report the mismatch instead of inventing an endpoint or browser-only substitute.

## Required implementation

### 1. Preserve idempotency across unknown outcomes

The current API client generates `crypto.randomUUID()` inside every call to
`createKnowledgeSource()` and `reingestKnowledgeSource()`. A retry therefore receives a new key even
when the previous network or server outcome is unknown.

Move idempotency-key ownership from the low-level request method to the user-initiated logical
operation.

Required behavior:

- Generate one opaque key immediately before the first submission of a logical create or
  re-ingestion operation.
- Pass that key explicitly to the admin API boundary.
- Retain the key only when the request outcome is unknown, including network failure or a server
  response where the operation may already have committed.
- An explicit retry with an identical payload must reuse that retained key.
- If the administrator changes any create payload field after an unknown outcome, discard the old
  key and generate a new one for the changed operation.
- A definitive validation, forbidden, not-found or idempotency-conflict response must not be
  silently retried.
- A successful response completes the operation and clears its retained key.
- Opening a later, independent create or re-ingestion action must generate a fresh key.
- Do not derive keys from source content or place them in URLs, logs, telemetry, browser storage or
  user-visible text.
- Do not automatically retry mutations.

Use an explicit API contract such as a required `idempotencyKey` argument or operation options
object. The low-level client must not manufacture a replacement key when the caller is retrying an
existing logical operation.

For an unknown create outcome, keep the form values and show safe guidance that the result is
unknown. Offer only actions that preserve correctness, such as retrying the identical request with
the retained key or refreshing authoritative state before beginning a changed operation.

For an unknown re-ingestion outcome, keep the dialog or a clear operation state and allow an
identical retry with the retained key. Do not create a new logical operation merely because the
first response was lost.

### 2. Preserve and announce the immediate creation outcome

The successful `202` creation response contains the authoritative source, latest job and
`active_job_reused` flag. The current implementation navigates to detail and loses that immediate
result during the subsequent refetch.

After successful creation:

- continue to navigate to the canonical detail route;
- still fetch authoritative detail from the backend;
- carry only the safe operation outcome needed by the destination, not source content;
- announce whether a new ingestion job was queued or an existing canonical source/job was reused;
- ensure the announcement uses an accessible status region and receives focus when appropriate;
- ensure refresh or direct navigation does not fabricate a creation outcome;
- do not persist the outcome or source content in the URL, local storage or session storage.

React Router navigation state is acceptable when it contains only a source identifier and a stable
result enum. Validate that the state belongs to the current route source before displaying it.

### 3. Add required per-source list actions

Every populated knowledge-source card or row must expose accessible actions for:

- view details;
- enable or disable retrieval;
- request re-ingestion;
- delete.

Reuse the existing detail mutation behavior and confirmation dialog rather than creating parallel
business rules.

Requirements:

- Action accessible names include the source name.
- Disabling requires confirmation and accurately explains that indexed content remains stored.
- Re-ingestion and deletion require confirmation.
- Enabling may use the same dialog system but must describe the committed representation accurately.
- Pending actions disable conflicting actions for that source and prevent duplicate requests.
- Successful retrieval changes update the affected card from the authoritative response.
- Successful re-ingestion updates its latest job and announces whether the job was queued or reused.
- Successful deletion updates the collection total, corrects an invalid final page, and refreshes the
  Assistant knowledge-source count.
- Active-ingestion conflict retains the source and shows a safe actionable message.
- A stale or late response must not overwrite a newer confirmed source state.
- List mutations must use the same idempotency and error semantics as detail mutations.

Extract a focused shared action/dialog component only if it reduces duplicated rules between list
and detail. Do not introduce a general data-grid or mutation framework.

### 4. Complete source and ingestion operational detail

The detail page must display the supported operational fields already validated by the API client.

Source details:

- created timestamp;
- updated timestamp;
- type;
- retrieval state;
- normalized URL or read-only direct text.

Latest-ingestion details:

- status;
- current step when present;
- created timestamp;
- started timestamp when present;
- completed timestamp when present;
- safe failure code when present;
- safe failure message when present.

For a failed job, provide concise recovery guidance that re-ingestion may be attempted after the
underlying source is available. Do not claim that failure removed the previous committed
representation.

Continue to distinguish no job, queued, pending, running, completed, failed and cancelled states.
Do not expose raw provider payloads, HTML, chunks, embeddings, stack traces or database details.

### 5. Make dialog focus behavior deterministic

All source-action dialogs must restore focus after:

- cancellation button;
- Escape dismissal;
- successful enable or disable;
- successful re-ingestion;
- successful deletion when a stable list target remains;
- recoverable mutation failure after the dialog is eventually dismissed.

Capture the initiating element or use the established PR 13B dialog pattern. Close the native
dialog through its supported lifecycle before unmounting where necessary. When deletion removes the
trigger, move focus to a stable collection heading, status notice, adjacent source action or “Add
knowledge source” control.

Requirements:

- focus remains contained while the modal is open;
- pending state is announced and buttons are disabled;
- every icon or text action has an unambiguous accessible name;
- no focus is left on a removed node or reset to the document body;
- success and failure announcements remain perceivable without relying on color.

### 6. Complete deterministic Storybook coverage

Preserve existing fixed fictional data and fake API boundaries. Add or refine stories for:

- queued ingestion detail;
- pending re-ingestion mutation with disabled controls;
- new re-ingestion job result;
- reused active-job result;
- enabled and disabled retrieval states;
- deletion confirmation before submission;
- active-ingestion deletion conflict;
- complete failed-ingestion operational detail and recovery guidance;
- creation result announcement for queued and reused outcomes where practical.

Stories must make no network requests, depend on no cookie or live authentication state, use no
current time, and share no mutable state.

### 7. Complete API-boundary regression coverage

Extend `apps/admin/src/api/adminApi.test.ts` to cover:

- the caller supplies creation and re-ingestion idempotency keys;
- two independent logical operations use different keys;
- an identical explicit retry uses the same key;
- the low-level client does not replace a supplied key;
- direct-text and URL create request bodies;
- URL response validation, including unsupported schemes, credentials and fragments;
- malformed UUIDs, timestamps, nullable job fields and pagination metadata;
- every supported source, retrieval, ingestion-status and ingestion-step enum;
- `202` creation/re-ingestion and `204` deletion status enforcement;
- cancellation forwarding for every read method where behavior differs;
- safe mapping of `401`, `403`, `404`, validation, idempotency conflict and active-ingestion
  conflict;
- raw failure bodies and messages remain discarded.

Do not assert only that a mock was called. Verify the observable returned value or safe error as
well as exact path, method, credentials, headers and body.

### 8. Complete rendered workflow regression coverage

Extend rendered application tests through the API boundary where practical.

Required cases:

#### Routing and list

- authenticated Assistant knowledge route;
- Assistant/source not-found and cross-Assistant-safe presentation;
- loading, populated, empty, retryable error and manual refresh;
- source pagination and correction after deleting the last item on a page;
- list actions have unambiguous accessible names;
- source content never appears in list rendering.

#### Creation

- successful direct-text creation;
- successful single-page URL creation with no hidden direct-text field in the payload;
- source-type switching preserves values without submitting contradictory fields;
- required and bounded name/direct text;
- invalid scheme, embedded credentials and fragment rejection;
- duplicate submission prevention;
- dirty-form navigation warning;
- queued and reused creation announcements;
- unknown outcome followed by identical retry reuses the key;
- editing the payload after an unknown outcome creates a new key;
- validation/network/conflict failures retain form values and focus the error summary;
- no content or idempotency key enters browser storage or route URLs.

#### Retrieval, re-ingestion and deletion

- enable and disable confirmation with exact state payloads;
- failed state change retains the prior confirmed state;
- repeated or out-of-order responses cannot regress newer state;
- re-ingestion pending state prevents duplicate submission;
- new-job and active-job-reuse announcements;
- identical unknown-outcome re-ingestion retry reuses the key;
- idempotency conflict refresh guidance;
- successful deletion updates the collection and Assistant count;
- active-ingestion conflict retains the source;
- already-missing and cross-Assistant-safe responses;
- `401` invalidates the session while `403` preserves it;
- focus restoration after cancellation, success and failure;
- deletion moves focus to a stable target when its trigger no longer exists.

Use precise semantic assertions. Do not weaken existing PR 13A/13B tests or mock away request
construction, response validation, state reconciliation or focus behavior.

### 9. Documentation and pull-request evidence

Update `apps/admin/README.md` only where retry behavior or operational detail needs clarification.

Document:

- identical unknown-outcome retries reuse the same idempotency key;
- changed payloads become new logical operations;
- creation/re-ingestion queued versus reused announcements;
- failed-ingestion recovery guidance;
- current exclusions remain unchanged.

Update PR #66's description after verification so it lists commands actually run and their results.
Do not leave “Not run” when checks have been executed. Do not claim live backend/worker scenarios
were completed unless they were actually observed.

---

## Acceptance criteria

- [ ] Creation and re-ingestion idempotency keys are owned by logical operations, not regenerated
  inside every API call.
- [ ] Identical explicit retries after unknown outcomes reuse the original key.
- [ ] Changed payloads and later independent operations receive new keys.
- [ ] Unknown outcomes provide safe retry-or-refresh guidance and never encourage an unsafe new-key
  retry.
- [ ] Successful creation announces queued versus reused ingestion without putting source content
  in navigation state, URLs or browser storage.
- [ ] Every populated source card exposes view, retrieval-state, re-ingestion and delete actions.
- [ ] List and detail mutations share one authoritative behavior and error model.
- [ ] Successful list mutations reconcile the source, collection total and Assistant source count.
- [ ] Source detail shows created/updated timestamps and complete supported ingestion lifecycle
  fields.
- [ ] Failed ingestion shows safe recovery guidance without implying loss of committed knowledge.
- [ ] Dialog focus is restored deterministically after cancellation, success and recoverable failure.
- [ ] Successful deletion places focus on a stable remaining target.
- [ ] Pending mutations prevent duplicate actions and remain screen-reader understandable.
- [ ] Storybook includes queued, pending, new-job, reused-job, failed-detail and deletion states.
- [ ] API tests verify explicit key ownership, key reuse and fresh-key boundaries.
- [ ] Rendered tests cover URL creation, pagination, enable/failure reconciliation, successful
  deletion, session errors, dirty navigation, concurrency and focus restoration.
- [ ] Direct text, credentials, full sensitive URLs, cookies, idempotency keys and raw backend errors
  are never logged, stored or rendered unsafely.
- [ ] No backend, RAG UI or public Assistant widget behavior is changed.
- [ ] Existing PR 13A and PR 13B administrator workflows remain passing.
- [ ] Admin tests, type-check, lint, production build and Storybook build pass.
- [ ] GitHub Actions required checks pass.
- [ ] PR #66 accurately reports verification performed.
- [ ] `git diff --check` passes.

## Verification commands

Run from the repository root using the actual focused test paths present on the branch.

```bash
git status -sb

# Focused behavior during development
npm test --workspace @ai-discovery-assistant/admin -- src/api/adminApi.test.ts
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx

# Complete admin verification
npm run test:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run lint:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

# Backend contract regression; no backend production changes are expected
cd apps/backend
venv/bin/python -m pytest -q tests/test_knowledge_source_api.py
cd ../..

git diff --check
git status -sb
```

Also inspect PR #66's GitHub Actions run and confirm every required check is complete and successful.

Where a local administrator session, backend, worker and disposable source are available, manually
verify:

1. Create direct-text and URL sources and observe queued/reused announcements.
2. Simulate an unknown create outcome and confirm an identical retry reuses one idempotency key.
3. Change the payload and confirm the next operation receives a new key.
4. Enable and disable retrieval from both list and detail.
5. Request re-ingestion from list and detail and observe new/reused outcomes.
6. Delete a terminal source and confirm collection/count/focus reconciliation.
7. Attempt deletion during active ingestion and confirm the source remains.
8. Navigate every dialog by keyboard, cancel with Escape and verify focus restoration.
9. Expire the session and confirm a protected mutation returns safely to login.
10. Confirm no source content or idempotency key appears in URLs, browser storage, console output or
    error UI.

Do not report manual scenarios as passed when the required services or instrumentation were not
available.

## Completion report

Report:

1. Existing PR branch and files changed.
2. Review findings resolved and behavior-focused tests added, including expected initial failures.
3. Idempotency-key lifecycle and unknown-outcome design.
4. List/detail reconciliation and focus-restoration design.
5. Documentation or public-interface changes; explicitly state that backend contracts and
   dependencies were unchanged when applicable.
6. Commands actually run and their final results.
7. GitHub Actions and manual scenarios actually observed.
8. Remaining limitations, unverified behavior, deviations and risks.
