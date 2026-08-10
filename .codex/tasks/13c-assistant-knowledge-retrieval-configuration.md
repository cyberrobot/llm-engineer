# PR 13C — Assistant Knowledge & Retrieval Configuration

## Repository state

Expected branch:

`feature/13c-assistant-knowledge-retrieval-configuration`

Base branch:

`main`, after PR 13B — Admin Assistant Management Foundation is merged

Worktree:

Frontend

Dependencies:

- PR 13A — Admin Application Foundation must be merged.
- PR 13B — Admin Assistant Management Foundation must be merged.
- PR 11B — Redmoor Knowledge Source Management must be merged.
- PR 11B.1 — Knowledge Source Management Hardening must be merged.
- PR 11F — Administrator Assistant Management API must be merged.

At the time this specification was written, the implementation branch contains the required
administrator API under `/admin/assistants/{assistant_id}/knowledge-sources`. It supports direct-text
and single-page URL sources, source listing and detail, retrieval enable/disable, re-ingestion and
guarded deletion.

Codex must verify those contracts on the implementation branch before changing the admin
application. If PR 13B or the backend knowledge-source API is absent, stop and report the missing
dependency. Do not recreate either dependency inside this PR.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/13a-admin-application-foundation.md`
- `.codex/tasks/13b-admin-assistant-management.md`
- `.codex/tasks/11b-redmoor-knowledge-source-management.md`
- `apps/admin/README.md`
- `apps/admin/package.json`
- `apps/admin/src/App.tsx`
- `apps/admin/src/api/adminApi.ts`
- `apps/admin/src/features/assistants/`
- Existing admin authentication, routing, test utilities and Storybook setup
- `apps/backend/AGENTS.md`
- `apps/backend/assistant/api/knowledge_sources.py`
- `apps/backend/assistant/schemas/knowledge_source.py`
- `apps/backend/assistant/domain/knowledge_source.py`
- `apps/backend/assistant/domain/assistant.py`
- `apps/backend/tests/test_knowledge_source_api.py`
- `apps/backend/docs/knowledge-source-management.md`, if present

### Primary change area

- `apps/admin/src/features/knowledge-sources/`, or the equivalent feature location established by
  PR 13B
- `apps/admin/src/api/adminApi.ts`
- Admin application routes, navigation and styles only where required
- Admin component, API-boundary, routing and Storybook tests
- `apps/admin/README.md`

### Canonical implementation examples

- PR 13B Assistant pages for authenticated routing, feature state, safe errors, pagination,
  mutation handling and destructive confirmation
- Existing admin API client for credentialed requests, `AbortSignal`, response validation and
  session-expiry mapping
- Backend knowledge-source schemas and API tests for the authoritative wire contract
- Existing admin Storybook stories for deterministic, network-free states

### Relevant symbols

- `AdminApi`
- `AdminApiError`
- `createAdminApi`
- `AssistantDetail`
- `KnowledgeSource`
- `KnowledgeSourceType`
- `DocumentRetrievalState`
- `KnowledgeSourceResponse`
- `KnowledgeSourceListResponse`
- `KnowledgeSourceJobResponse`
- `CreateKnowledgeSourceRequest`
- `UpdateKnowledgeSourceRequest`
- `IngestionStatus`
- `IngestionStep`

### Expected change surface

- Typed knowledge-source models and API methods in the existing admin API boundary
- Assistant-scoped knowledge-source list and detail routes
- Direct-text and URL source creation
- Source retrieval-state controls
- Re-ingestion and guarded deletion actions
- Loading, empty, error, not-found and ingestion lifecycle states
- Tests, deterministic stories and admin documentation

### Excluded areas

- Backend domain, API, persistence, worker or migration changes
- Public Assistant widget and internal RAG UI changes
- Prompt, model, temperature or token configuration
- Similarity thresholds, top-K, reranking, hybrid-search weights or embedding selection
- Chunk size, chunk overlap, parser or crawler configuration
- File upload, sitemap, recursive crawl or multi-page website ingestion
- Editing source content, URL or name after creation
- Raw document, chunk, embedding or provider-payload inspection
- Ingestion cancellation, scheduling or manual retry-policy configuration
- Chat preview, retrieval debugging, evaluations, analytics or audit logs
- Bulk actions, source ordering, source sharing or moving sources between assistants
- A general-purpose data-grid, form framework, polling framework or notification system

### Unknowns Codex must verify

- The final PR 13B route hierarchy and edit-page composition.
- Whether knowledge management is a dedicated assistant sub-route, tabs within Assistant detail, or
  another established nested layout.
- Exact backend JSON key casing and response fields.
- The complete ingestion status set and which statuses the backend treats as active or terminal.
- Pagination order and limits.
- Safe structured error codes for unknown assistants/sources, idempotency conflicts, active
  ingestion and validation failures.
- Whether the existing frontend API helper sends an `Origin` header implicitly through the browser
  only; frontend code must not attempt to forge it.
- Whether an established accessible dialog implementation exists after PR 13B.
- Whether the frontend has a query/cache library. Reuse it if present; do not add one solely for
  this feature when the existing state approach remains suitable.
- Whether live ingestion refresh is supported by an existing application mechanism. If not, use an
  explicit refresh action; bounded polling is optional only when implemented accessibly and safely.

---

## Objective

Replace the Knowledge Sources placeholder with an authenticated, assistant-scoped knowledge and
retrieval management experience.

An administrator must be able to:

- open an Assistant's knowledge configuration;
- see which direct-text and URL sources belong to that Assistant;
- understand each source's retrieval state and latest ingestion state;
- create a direct-text or single-page URL source;
- inspect the supported details of an existing source;
- enable or disable that source for retrieval without deleting indexed content;
- request re-ingestion without creating a duplicate source;
- delete a source when no ingestion is active.

“Retrieval configuration” in this PR means choosing which Assistant-owned knowledge sources are
enabled for retrieval. The backend does not expose per-Assistant similarity, ranking, chunking,
embedding or model settings. The admin UI must not imply that those controls exist.

The implementation must extend the admin shell, authentication, Assistant management, API client,
styling and test conventions established by PRs 13A and 13B.

## Current architecture

The backend owns knowledge-source validation, Assistant ownership, durable source persistence,
canonical document linkage, ingestion jobs, idempotency, retrieval filtering and safe deletion.
Sources are strictly nested under an Assistant. Cross-Assistant lookups use not-found semantics and
must not reveal that another Assistant owns a source.

Supported source types are:

- `direct_text`: a bounded, durable UTF-8 text body;
- `url`: one normalized absolute HTTP(S) page, not a crawler.

Every newly created source starts with retrieval enabled according to the current backend domain and
queues ingestion asynchronously. A source records the latest ingestion job, which may expose status,
current step, timestamps and safe failure information. Disabling retrieval preserves the indexed
representation but excludes it from production retrieval; enabling it restores the currently
committed representation without requiring re-ingestion.

The browser communicates only through the administrator HTTP API. It never imports backend modules,
reads the HTTP-only cookie, calls repositories, performs ingestion, computes retrieval eligibility,
or stores source content locally as a substitute for server persistence.

## Required implementation

### 1. Establish the Assistant knowledge route

Add an authenticated Assistant-scoped route using the hierarchy established by PR 13B.

Preferred routes are:

```text
/admin/assistants/:assistantId/knowledge
/admin/assistants/:assistantId/knowledge/new
/admin/assistants/:assistantId/knowledge/:sourceId
```

If PR 13B established a different nested-resource convention, follow it consistently. Do not add a
second routing hierarchy.

Provide a clear “Knowledge” or “Knowledge & retrieval” entry point from the Assistant edit/detail
experience. The page must identify the current Assistant by its authoritative name and provide a
route back to Assistants.

Unknown Assistant IDs and unknown or cross-Assistant source IDs must render explicit not-found
states with safe navigation. They must not appear as generic server errors and must not disclose
cross-Assistant ownership.

The top-level Knowledge Sources navigation item introduced as a placeholder by PR 13A may link to
the Assistants list with guidance to select an Assistant. Do not create an unscoped all-Assistant
source browser because the backend contract is Assistant-scoped.

### 2. Extend the existing admin API boundary

Add typed methods matching the backend exactly:

- list sources for one Assistant with bounded pagination;
- retrieve one source within one Assistant;
- create a direct-text or URL source;
- update retrieval state only;
- request re-ingestion;
- delete one source.

Every request must:

- use the configured admin API base URL;
- include `credentials: 'include'` through the shared request helper;
- accept and forward an `AbortSignal`;
- use the exact Assistant and source identifiers in encoded path segments;
- send JSON content types only for JSON bodies;
- map structured failures into safe application errors;
- notify the existing authentication mechanism on confirmed session expiry;
- never log raw bodies, direct text, full sensitive URLs, cookies or backend exceptions.

Mutating requests rely on the browser's real `Origin` header and the backend's trusted-origin check.
Do not synthesize or configure an `Origin` header in application code.

Creation and re-ingestion must send a fresh opaque `Idempotency-Key` for each user-initiated logical
operation. The same key must be retained only while safely retrying that identical operation. A new
or edited payload must receive a new key. Prefer `crypto.randomUUID()` where supported by the
project's browser baseline. Do not derive keys from source content or expose them in the UI.

Do not automatically retry mutations. A request whose outcome is unknown may be retried only with
the same key and identical payload; otherwise show a safe outcome-unknown message and refresh the
authoritative list/detail before offering another operation.

### 3. Validate successful responses at runtime

No successful response may enter application state until it is validated.

Validate, at minimum:

- source and Assistant IDs as non-nil UUIDs where the backend uses UUIDs;
- exact owning Assistant ID matches the route Assistant;
- source type is `direct_text` or `url`;
- retrieval state is `enabled` or `disabled`;
- name is non-empty and within the supported bound;
- URL is present only for URL sources and is an absolute HTTP(S) URL;
- direct text is absent from list summaries;
- direct text is present only where permitted in direct-text detail/create responses;
- document ID is a non-empty string;
- timestamps are valid strings with timezone offsets;
- ingestion status and current step use known enum values;
- ingestion timestamps and failure fields have valid nullable shapes;
- `active_job_reused` is boolean;
- pagination values are non-negative, bounded and internally consistent.

Malformed `2xx` responses become `invalid_response`. A malformed item must reject the collection;
do not silently omit it. A response carrying a different Assistant ID must be rejected, not displayed.

For `204 No Content`, reject unexpected response shapes according to the existing API convention.

### 4. Implement the knowledge-source list

The Assistant knowledge page must include:

- page heading and current Assistant context;
- concise explanation that enabled sources may contribute to answers after successful ingestion;
- primary “Add knowledge source” action;
- paginated collection;
- loading, empty, retryable error and not-found states;
- explicit refresh action;
- accessible success/failure announcements for mutations.

Each row or card must show supported summary fields:

- source name;
- Direct text or URL type;
- URL host or safe URL presentation for URL sources;
- Enabled or Disabled retrieval state;
- latest ingestion status and current step when present;
- updated timestamp where useful;
- available actions.

Never render direct-text content in the list. Do not place full URL query strings in dense list UI
or analytics. If a full URL is available to an authenticated administrator, show it only in the
detail view with safe wrapping and an explicit external link treatment.

Use a semantic table where comparison is useful and a responsive treatment at narrow widths. Do
not rely on colour alone. Status labels must have readable text, and pending states must expose
`role="status"` or equivalent accessible semantics.

Supported per-source actions are:

- view details;
- enable or disable retrieval;
- re-ingest;
- delete.

Disable actions that conflict with a known queued or running mutation. Do not infer deletion safety
solely from stale frontend state; the backend remains authoritative.

### 5. Create a source

The creation route starts with a required source-type choice:

- Direct text
- Web page URL

Common field:

- Name, required after trimming, maximum 255 characters.

Direct-text field:

- Content, required and non-whitespace, maximum 100,000 characters according to the current backend
  domain.

URL field:

- Absolute HTTP or HTTPS URL for one page.

Changing source type must not accidentally submit hidden fields from the other type. If changing
type would discard entered content, require confirmation or make the discard explicit.

Client validation should provide immediate useful feedback while leaving final authority to the
backend. Reject empty names, empty text, over-limit text, non-HTTP(S) URLs and URLs containing
credentials. Explain that fragments are unsupported if the backend rejects them. Do not promise
that a syntactically valid URL is safe or retrievable; the backend performs network security checks.

Do not normalize or rewrite a submitted URL in a way that changes meaning. Display the normalized
URL returned by the server after success.

Prevent duplicate submission while pending. On `202 Accepted`:

- trust and validate the authoritative response;
- navigate to the source detail or Assistant knowledge page;
- indicate whether ingestion was queued or an existing canonical source/job was reused;
- refresh the source collection.

On failure, preserve the entered values, focus the first invalid field or error summary, map known
validation and idempotency conflicts safely, and never display raw backend details.

Warn before navigation when a dirty form would lose entered direct text. Do not persist drafts or
source content to local storage, session storage, URLs, telemetry or logs.

### 6. Show source detail and ingestion state

The detail route must retrieve the source from the backend rather than relying only on list state.

Display:

- source name and type;
- retrieval state;
- normalized URL for URL sources;
- direct text for direct-text sources in a bounded, read-only presentation;
- canonical document identifier only if useful for administrator support;
- created and updated timestamps;
- latest ingestion status, current step and lifecycle timestamps;
- safe failure code/message when supplied by the administrator API;
- whether the latest creation/re-ingestion request reused an active job, when present in the
  immediate response.

Do not render HTML from source content. Direct text must be displayed as text, not interpreted
markup. Long content and URLs must wrap without breaking the layout.

The UI must distinguish:

- no ingestion job reported;
- queued;
- running, with current step when available;
- completed;
- failed, with safe recovery guidance;
- cancelled or any other status verified in the backend enum.

Do not claim that enabled means indexed, that completed means every query will retrieve the source,
or that failed re-ingestion removed the previously committed representation.

### 7. Configure retrieval participation

Provide one explicit control per source using the backend's `PATCH` contract:

```json
{"retrieval_state":"enabled"}
```

or:

```json
{"retrieval_state":"disabled"}
```

The request body must contain no unsupported mutable fields.

Explain the semantics accurately:

- Enabled: the source's currently committed knowledge may participate in this Assistant's
  retrieval.
- Disabled: stored knowledge remains present but is excluded from retrieval.

Require confirmation before disabling an enabled source because it can immediately affect answers.
Enabling need not require confirmation. Both operations must prevent duplicate submission, wait for
server confirmation, reconcile list and detail state, and retain the prior confirmed state after
failure.

Repeated requests must converge on the server-confirmed state. A late response from an older
request must not overwrite a newer confirmed state.

Do not add controls for top-K, similarity thresholds, chunking, reranking, embeddings, models or
global retrieval settings. Do not describe enable/disable as deleting or re-ingesting content.

### 8. Request re-ingestion

Re-ingestion is an explicit mutation and must require confirmation. Explain that it reprocesses the
persisted direct text or fetches the configured single page again while retaining the source
identity.

Requirements:

- send a fresh idempotency key for the logical request;
- prevent concurrent duplicate clicks;
- accept `202 Accepted`;
- display whether a new job was queued or an active job was reused;
- update the latest-job presentation from the authoritative response;
- retain prior committed knowledge when the new job later fails, without claiming backend state
  beyond the contract;
- map idempotency conflicts and not-found responses safely.

Re-ingestion must not create a source, change retrieval state, edit source configuration, or claim
to cancel an active job.

When the UI has no safe live-update mechanism, offer an explicit refresh button. If bounded polling
is added, it must:

- run only while the page is visible and the latest job is active;
- stop on terminal state, navigation, session expiry or component unmount;
- use abortable requests;
- avoid overlapping requests;
- avoid noisy announcements on every poll;
- fall back to manual refresh after repeated failures.

### 9. Delete safely

Deletion is destructive and must use an accessible confirmation dialog identifying the source by
name. Explain that deletion removes the source and its owned indexed representation and is blocked
while ingestion is queued or running.

Do not remove the source from confirmed UI state until the server returns `204 No Content`.

Handle:

- successful deletion;
- `active_ingestion` conflict;
- already missing source;
- unknown or cross-Assistant source;
- expired session or forbidden action;
- network, server and malformed-response failures.

After success, invalidate or refresh the Assistant detail count and knowledge-source collection,
close the dialog, navigate away from a deleted detail route, and restore focus to a stable location.
Treat a repeated delete that reports not found as already absent only when doing so matches the
existing PR 13B deletion convention.

Do not offer implicit ingestion cancellation or a force-delete control.

### 10. State, concurrency and cancellation

Reuse the state/query approach established by PR 13B. Use stable Assistant-scoped identities for
collection and detail state so data from one Assistant can never appear under another.

Requirements:

- abort superseded list/detail requests on route or pagination changes;
- ignore aborts without showing failure notifications;
- clear stale errors before a deliberate retry;
- prevent concurrent duplicate mutations;
- invalidate or update Assistant detail, source list and source detail after relevant mutations;
- never replay mutations during ordinary cache refresh;
- never let stale mutation responses overwrite newer state;
- preserve the current page where valid, but move to the previous valid page after deleting its last
  item;
- do not retain direct-text details longer or more broadly than needed.

### 11. Error handling and security

Use the safe application-level categories established by PRs 13A and 13B:

- unauthenticated;
- forbidden;
- not found;
- invalid request or validation;
- conflict;
- rate limited, if returned by the verified contract;
- network;
- server;
- invalid response.

Preserve backend error codes needed for safe decisions, including
`knowledge_source_not_found`, `assistant_not_found`, `idempotency_key_conflict` and
`active_ingestion`, after verifying their current names.

A confirmed `401` must use the existing session-expiry mechanism. A `403` must not automatically
log out the administrator. Raw response bodies, stack traces, SQL/provider details, fetched HTML,
direct text, embeddings, cookie values and URLs containing sensitive query data must not be logged,
rendered as errors or sent to browser telemetry.

Frontend visibility and disabled buttons are not authorization boundaries. Every action must still
go through the authenticated backend endpoint.

### 12. Accessibility and responsive behaviour

The complete workflow must support keyboard and screen-reader use.

Include:

- semantic headings, landmarks, tables and lists;
- labelled source-type, name, content and URL controls;
- associated validation messages and an error summary where useful;
- focus on the first invalid field or summary after failed submission;
- visible focus indicators;
- accessible loading and mutation-pending states;
- unambiguous action names containing the source name;
- dialog focus containment, Escape handling and focus restoration;
- text labels in addition to colour for retrieval and ingestion state;
- responsive layout without horizontal page overflow at normal mobile widths;
- safe wrapping for long URLs and direct text.

Use the accessible dialog approach already established by PR 13B. Do not create a second dialog
system or a hand-rolled focus trap.

### 13. Storybook

Add deterministic stories for reusable knowledge-source states.

At minimum cover:

- populated list with direct-text and URL sources;
- empty list;
- list loading and error;
- direct-text creation form;
- URL creation form;
- validation errors;
- source detail with completed ingestion;
- queued/running ingestion;
- failed ingestion with safe message;
- enabled and disabled retrieval states;
- re-ingestion confirmation and pending state;
- delete confirmation and active-ingestion conflict.

Stories must use fixed fictional identifiers, timestamps, content and URLs. They must not contact the
backend, depend on cookies or live authentication, use real source content, depend on current time,
or leak mutation state between stories.

### 14. Documentation

Update `apps/admin/README.md` with:

- Assistant-scoped knowledge routes;
- supported direct-text and single-page URL sources;
- creation limits and asynchronous ingestion behaviour;
- retrieval enable/disable semantics;
- re-ingestion and active-job reuse;
- deletion conflicts;
- authentication and trusted-origin requirements;
- safe handling of source content;
- local verification commands;
- explicit exclusions, especially file upload, crawling and numeric/model retrieval controls;
- troubleshooting for expired sessions, invalid responses, failed ingestion, idempotency conflict
  and active-ingestion deletion conflict.

Do not document backend capabilities or endpoint shapes until verified against implementation.

## Acceptance criteria

- [ ] The PR is based on merged PR 13B and extends its admin application without replacing its
  routing, authentication, API or styling foundations.
- [ ] The Knowledge Sources placeholder becomes a truthful Assistant-selection entry point or is
  replaced by Assistant-scoped knowledge navigation.
- [ ] Administrators can open knowledge configuration for a specific Assistant.
- [ ] All source reads and mutations use the real authenticated, Assistant-scoped backend contract.
- [ ] Requests use `credentials: 'include'`, support cancellation and safely map session expiry.
- [ ] Mutations rely on the browser's real trusted-origin behaviour and do not forge `Origin`.
- [ ] Source list and detail responses are runtime validated before entering state.
- [ ] A response whose `assistant_id` differs from the route Assistant is rejected.
- [ ] Malformed successful responses produce a safe invalid-response state.
- [ ] List pagination is bounded, validated and remains usable after deletion.
- [ ] Direct-text content is never present in list UI, URLs, browser storage, logs or error messages.
- [ ] Administrators can create a bounded direct-text source and receive the queued/reused ingestion
  result.
- [ ] Administrators can create a single-page absolute HTTP(S) URL source.
- [ ] Hidden fields from the unselected source type are not submitted.
- [ ] Duplicate submissions are prevented and creation/re-ingestion use safe idempotency keys.
- [ ] Dirty direct-text forms warn before discarding content.
- [ ] The UI presents latest ingestion state without claiming unsupported progress or retrieval
  guarantees.
- [ ] Administrators can disable retrieval without deleting indexed content.
- [ ] Administrators can enable the currently committed representation without forcing
  re-ingestion.
- [ ] Disabling requires confirmation and state changes only after server confirmation.
- [ ] No similarity, top-K, chunking, reranking, embedding or model controls are invented.
- [ ] Administrators can request re-ingestion and see whether a new or existing active job was used.
- [ ] Administrators can delete a source after confirmation when the backend permits it.
- [ ] Active-ingestion deletion conflicts retain the source and show a safe actionable message.
- [ ] Unknown and cross-Assistant resources use indistinguishable not-found presentation.
- [ ] Late or aborted requests do not overwrite newer state or display spurious failures.
- [ ] A `403` does not invalidate an otherwise valid session.
- [ ] No raw backend/provider/database details or sensitive source data are rendered or logged.
- [ ] The interface is keyboard accessible, screen-reader understandable and usable at mobile
  widths.
- [ ] Storybook stories are deterministic and make no network requests.
- [ ] Tests exercise request construction, validation and primary workflows through the API
  boundary rather than only mocking feature hooks.
- [ ] Admin documentation accurately describes the implemented scope and exclusions.
- [ ] Admin lint, type-check, tests, production build and Storybook build pass.
- [ ] Existing backend, RAG UI and public Assistant widget behaviour remain unchanged.
- [ ] `git diff --check` passes.

## Tests to add or update

Use Vitest, React Testing Library, `userEvent` and the request-mocking approach established by PRs
13A and 13B.

### API boundary

- Exact Assistant-scoped paths, methods, headers and request bodies.
- `credentials: 'include'` and `AbortSignal` forwarding.
- List pagination query construction.
- Fresh idempotency key per logical creation/re-ingestion operation and retained key only for an
  identical explicit retry.
- No automatic mutation retry.
- Direct-text and URL response validation.
- List omission of direct text.
- Assistant ownership mismatch rejection.
- Invalid UUIDs, source/retrieval/status/step enums, timestamps, URLs, nullable job fields,
  pagination metadata and unexpected shapes.
- `202` creation/re-ingestion and `204` deletion handling.
- Safe mapping of authentication, forbidden, not-found, validation, idempotency and active-ingestion
  conflicts.
- Confirmation that raw failure bodies are discarded.

### Routing and list

- Authenticated Assistant knowledge route.
- Assistant and cross-Assistant source not-found states.
- Knowledge placeholder/entry-point navigation.
- Loading, populated, empty, retryable error and manual refresh states.
- Direct text absent from list rendering.
- Source type, retrieval state and ingestion status accessible labels.
- Pagination and last-item deletion page correction.
- Session expiry and `403` distinction.

### Creation

- Required and bounded name.
- Required non-whitespace and bounded direct text.
- Absolute HTTP(S) URL validation, unsupported schemes, credentials and fragments.
- Type switching does not submit contradictory payloads.
- Duplicate-submit prevention.
- Dirty-form navigation warning.
- Successful queued creation and canonical-source/job reuse.
- Retained form values and focus after safe validation/network/conflict errors.
- No source content written to browser storage or URLs.

### Detail and retrieval state

- Direct text rendered as text rather than HTML.
- Safe URL presentation and wrapping.
- No-job, queued, running, completed, failed and cancelled states verified from backend enums.
- Current ingestion step presentation.
- Disable confirmation and exact patch body.
- Successful enable/disable reconciliation.
- Failed retrieval-state change retains prior confirmed state.
- Repeated and out-of-order responses cannot regress confirmed state.

### Re-ingestion and deletion

- Re-ingestion confirmation and pending state.
- New job versus active-job reuse messaging.
- Idempotency conflict and unknown-outcome recovery.
- Optional polling lifecycle and cancellation if polling is implemented.
- Delete confirmation identifies the source.
- Successful deletion updates source list and Assistant source count.
- Active-ingestion conflict retains the source.
- Already-missing and cross-Assistant responses.
- Dialog focus restoration after success, cancellation and failure.

### Storybook and regressions

- Stories use fixed data and fake API boundaries.
- No story contacts the backend or depends on live authentication/current time.
- Existing authentication and Assistant management tests remain green.
- Existing public applications are unchanged.

Where practical, write each behaviour-focused regression first and confirm that it fails for the
expected missing behaviour before implementing production code.

## Verification commands

Run from the repository root. Use the actual focused test paths created by the implementation.

```bash
git status -sb

# Focused admin tests during development
npm run test:admin -- --run apps/admin/src/api/adminApi.test.ts
npm run test:admin -- --run apps/admin/src/features/knowledge-sources

# Complete admin verification
npm run lint:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run test:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

# Backend contract regression; frontend code must not require backend changes
cd apps/backend
venv/bin/python -m pytest -q tests/test_knowledge_source_api.py
cd ../..

git diff --check
git status -sb
```

If script names or the Python environment differ on the implementation branch, use the documented
repository equivalents and report the exact commands. Do not claim PostgreSQL, worker or retrieval
behaviour was reverified unless those suites were actually run successfully.

Before completion, manually verify where the local backend and worker are available:

1. Sign in as an administrator.
2. Open an Assistant and its Knowledge page.
3. On a private test Assistant, create a fictional direct-text source and observe queued ingestion.
4. Refresh until the authoritative terminal state appears.
5. Disable the source and confirm the disabled state survives refresh.
6. Re-enable it without requesting re-ingestion.
7. Create a fictional single-page URL source.
8. Request re-ingestion twice while a job is active and confirm the canonical source remains one
   item and active-job reuse is represented safely.
9. Attempt deletion during active ingestion and confirm the source remains present.
10. Delete a terminal source and confirm the list and Assistant source count update.
11. Open an unknown/cross-Assistant source route and confirm safe not-found presentation.
12. Expire the session and confirm the next protected request returns safely to login.
13. Confirm no source content appears in browser storage, request URLs, console logs or error UI.
14. Confirm Storybook stories make no backend requests.

## Completion report

Report:

1. Branch and files changed.
2. Behaviour-focused tests added, including the initial expected failures where practical.
3. Implemented routes, source workflows and important reuse decisions.
4. The exact verified backend contract and any differences from this specification's expected
   paths or fields.
5. Configuration, dependency, migration and public-interface changes; state explicitly when there
   are none.
6. Commands actually run and their final results.
7. Manual scenarios completed.
8. Known limitations, skipped checks, repository mismatches, deviations and remaining risks.
