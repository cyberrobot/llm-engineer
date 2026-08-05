PR 13B — Admin Assistant Management Foundation

Repository state

Expected branch

feature/13b-admin-assistant-management

Base branch

main

Worktree

Frontend

Dependencies

- PR 13A — Admin Application Foundation must be merged.
- PR 11A — Assistant Domain and Knowledge Scoping must be merged.
- An authenticated administrator-facing Assistant management API must exist before this PR can provide functional CRUD operations.

At the time this specification was written, main contains the Assistant domain and persistence model but does not appear to contain administrator-facing endpoints for listing, creating, updating, activating, deactivating, or deleting assistants.

Codex must inspect the current branch before implementation.

If the required backend API is still absent, stop and report the missing contract. Do not:

- invent endpoint paths;
- add temporary frontend-only persistence;
- use local storage as an assistant database;
- call backend repositories directly;
- add unplanned backend endpoints inside this frontend PR;
- mock successful operations in production code.

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/13a-admin-application-foundation.md
- apps/admin/README.md
- apps/admin/package.json
- apps/admin/src/
- Admin authentication API client and authentication provider
- Admin routing and shell implementation
- Existing admin test utilities and Storybook setup
- apps/backend/AGENTS.md
- apps/backend/assistant/domain/assistant.py
- apps/backend/assistant/domain/assistant_repository.py
- apps/backend/assistant/infrastructure/repositories/assistant.py
- Assistant persistence tests
- Any administrator-facing Assistant API schemas, routes and tests that exist on the implementation branch

Authoritative Assistant fields

The existing Assistant domain currently defines:

- id
- slug
- name
- status
- visibility
- created_at
- updated_at

The current enum values are:

status:

- active
- inactive
  visibility:
- public
- private

The slug is a lowercase, route-safe identifier matching the existing backend validation rules.

Do not add speculative fields such as:

- description;
- system prompt;
- model;
- temperature;
- maximum tokens;
- welcome message;
- suggested questions;
- retrieval configuration;
- widget configuration;
- publishing state;
- branding.

Those belong in later PRs only after their backend domains and contracts exist.

⸻

Objective

Replace the Assistants placeholder introduced by PR 13A with the first functional administrator-facing Assistant management experience.

An authenticated administrator must be able to:

- view existing assistants;
- understand their status and visibility;
- create an assistant;
- edit its supported identity and access fields;
- activate or deactivate an assistant;
- delete an assistant where the backend permits deletion.

The implementation must extend the existing admin application rather than replacing its routing, API client, authentication provider, shell, styling conventions or test infrastructure.

The result should establish a maintainable feature structure for future Assistant configuration PRs while remaining deliberately limited to the existing Assistant domain.

⸻

Scope

Included

- Assistants list route
- Create Assistant route
- Edit Assistant route
- Assistant detail retrieval where required for editing
- Typed Assistant API client methods
- Runtime validation of successful API responses
- Search or filtering only where supported by the backend contract
- Status and visibility display
- Create and edit forms
- Activate and deactivate actions
- Delete confirmation workflow
- Loading, empty, error and not-found states
- Session-expiry integration
- Accessible interaction patterns
- Responsive layouts
- Unit, component and API-boundary tests
- Deterministic Storybook stories
- Admin README updates

Excluded

- Knowledge-source management or assignment
- Document or chunk management
- Ingestion and re-ingestion
- Retrieval configuration
- Prompt or behaviour configuration
- Widget appearance
- Assistant preview or chat testing
- Publishing workflows beyond the existing active/inactive status
- Assistant duplication
- Export or import
- Analytics, conversations, evaluations or audit logs
- Bulk actions
- Drag-and-drop ordering
- Backend domain redesign
- Authentication changes unrelated to consuming protected Assistant endpoints
- General-purpose data-table or form framework development

⸻

Routes

Use the route hierarchy established by PR 13A.

Expected routes:

/admin/assistants
/admin/assistants/new
/admin/assistants/:assistantId/edit

If PR 13A established the authenticated application without the /admin prefix, preserve that convention instead of introducing a second hierarchy.

The existing Assistants navigation item must link to the functional list page.

Unknown assistant IDs must produce an explicit not-found state with a route back to the list. They must not be presented as generic network failures.

⸻

Required implementation

1. Create an Assistant feature boundary

Organise the implementation around the Assistant feature using the existing apps/admin conventions.

A reasonable structure is:

src/features/assistants/
api/
components/
pages/
validation/
types.ts

Use a different structure if PR 13A established another clear convention.

Pages and visual components must not call fetch directly. All network access must go through the admin API boundary.

Do not create speculative shared abstractions. Components should become shared only when they have genuine reuse within the current application.

2. Extend the admin API client

Add typed methods corresponding exactly to the merged backend contract.

Expected capabilities are:

- list assistants;
- retrieve one assistant;
- create an assistant;
- update an assistant;
- update status, if represented by a dedicated endpoint;
- delete an assistant.

Codex must verify:

- endpoint paths;
- HTTP methods;
- request bodies;
- response bodies;
- pagination structure;
- sorting behaviour;
- search parameters;
- error codes;
- conflict semantics;
- delete restrictions;
- authentication requirements.

Every request must:

- use the configured admin API base URL;
- include the HTTP-only session cookie through credentials: 'include';
- support AbortSignal;
- use safe error mapping;
- notify the existing authentication foundation when a response confirms session expiry;
- avoid logging raw payloads or backend errors.

Successful responses must be validated before entering application state. Validate:

- object and collection structure;
- UUID or identifier strings where applicable;
- non-empty names;
- valid slugs;
- known status values;
- known visibility values;
- timestamp strings;
- pagination metadata where present.

Malformed successful responses must become a safe invalid_response error.

Do not automatically retry mutations.

3. Implement the Assistants list page

Replace the placeholder with a page containing:

- page title;
- concise supporting description;
- primary “Create assistant” action;
- assistants collection;
- loading state;
- empty state;
- retryable failure state.

Each assistant row or card must show only supported fields:

- name;
- slug;
- status;
- visibility;
- updated timestamp where useful;
- available actions.

Use a semantic table on layouts where tabular comparison is useful. A responsive card treatment may be used at narrow widths.

Do not introduce a large third-party data-grid for this small domain.

Required actions:

- edit;
- activate or deactivate;
- delete where permitted.

Actions must remain keyboard accessible and must have unambiguous accessible names.

Do not rely on colour alone for status or visibility.

If the backend supports pagination, search or filtering, implement the supported contract. If it does not, do not simulate server capabilities or load an unbounded dataset under assumptions.

At minimum, status and visibility should be readable through consistent badges or text labels.

4. Implement creation

The create page must contain fields for:

- name;
- slug;
- status;
- visibility.

Use backend-supported defaults. Do not assume that new assistants should be active or public unless the backend explicitly defines those defaults.

Validation must mirror the backend rules sufficiently to provide useful feedback while treating the backend as authoritative.

Expected client validation:

- name is required after trimming;
- slug is required;
- slug uses lowercase route-safe segments;
- status is a supported enum value;
- visibility is a supported enum value.

Do not silently rewrite an invalid slug during submission.

A slug may be suggested from the name for convenience only if:

- the generated value remains editable;
- user edits are not overwritten;
- the implementation is deterministic;
- the backend still validates uniqueness and format.

Prevent duplicate submission while the request is pending.

On success:

- update or invalidate the Assistant list;
- navigate to the canonical edit page or list page;
- show a non-sensitive success message where consistent with the existing admin application.

On failure:

- retain entered values;
- map validation errors to fields where the backend contract supports it;
- show slug conflicts clearly;
- distinguish safe network, server and authentication errors;
- never expose raw backend details.

5. Implement editing

The edit route must load the current Assistant from the backend.

Required states:

- loading;
- loaded;
- not found;
- retryable failure;
- session expired.

The form must support only fields the backend permits administrators to change.

Do not assume that the Assistant ID, creation timestamp or immutable system fields are editable.

If the backend treats the slug as immutable after creation, display it read-only. If slug updates are supported, preserve conflict and validation handling.

On successful update:

- update the cached detail;
- update or invalidate the list;
- keep the UI consistent with the authoritative response;
- show confirmation without navigating unexpectedly.

The page must warn before discarding unsaved changes when navigating away or cancelling, using the existing router’s supported blocking mechanism where reliable. Do not add fragile global browser interception for unchanged forms.

6. Status changes

Active and inactive are operational states, not decorative labels.

Provide a clear activate/deactivate action using the exact backend operation.

Requirements:

- require confirmation before deactivation if it can make a public assistant unavailable;
- describe the immediate effect without making unsupported claims;
- disable duplicate action while pending;
- prevent stale responses from overwriting newer state;
- reconcile the UI with the server response;
- show a safe failure message and retain the prior confirmed state on failure.

Do not optimistically display a new status unless rollback behaviour is fully reliable. A pending state followed by server confirmation is acceptable and safer.

7. Visibility changes

Visibility may be edited through the main Assistant form if supported by the backend update contract.

Use the terms exposed by the domain:

- Public
- Private

Provide concise explanatory copy:

- public assistants may be available through public interfaces;
- private assistants are not publicly accessible.

Do not claim that visibility alone provides complete authorization or publishing control.

Any material transition warning must be based on actual backend semantics.

8. Delete workflow

Deletion is destructive and must require explicit confirmation.

The confirmation must identify the Assistant by name and explain that deletion may be unavailable when dependent records exist.

Use the backend’s deletion semantics exactly.

Required handling:

- success;
- not found;
- conflict or dependency rejection;
- unauthorized or expired session;
- network or server failure.

Do not remove the item permanently from the UI until the server confirms deletion.

If the Redmoor assistant or any seeded Assistant is protected from deletion, reflect the backend rejection safely. Do not hard-code frontend protection unless the backend contract explicitly identifies it.

After successful deletion:

- invalidate or update the list;
- close the dialog;
- return to the list if deletion originated from the edit route;
- move focus to an appropriate stable location.

9. Query and mutation state

Reuse TanStack Query or the state mechanism established by PR 13A if present.

Use stable query keys for:

- Assistant collection;
- individual Assistant details.

Mutations must correctly invalidate or update affected queries.

Avoid:

- duplicated request state in component-local state;
- background retries of destructive mutations;
- stale detail pages after updates;
- concurrent submissions;
- cache entries containing malformed API responses.

Cancellation during navigation must not produce visible error notifications.

10. Accessibility and responsive behaviour

The complete flow must be usable with keyboard and screen readers.

Requirements include:

- semantic headings and landmarks;
- labelled form controls;
- associated validation messages;
- focus on the first invalid field or error summary;
- visible focus indicators;
- accessible pending states;
- correctly labelled icon buttons;
- focus containment and restoration for confirmation dialogs;
- no colour-only status communication;
- no horizontal overflow at normal mobile widths.

Use an established accessible dialog implementation already present in the repository. If none exists, prefer a maintained accessible library over creating focus-trap and dismissal behaviour manually.

11. Storybook

Add deterministic stories for reusable states.

At minimum:

- Assistant list with several records;
- empty list;
- list loading;
- list error;
- create form;
- edit form;
- validation errors;
- status badges;
- delete confirmation;
- pending status action.

Stories must use fixed fictional data and fake API boundaries.

No story may:

- contact the backend;
- depend on cookies;
- use live authentication;
- depend on current time without fixing it;
- mutate shared state across stories.

12. Documentation

Update apps/admin/README.md with:

- Assistant management scope;
- routes;
- backend API dependency;
- supported fields;
- local development expectations;
- verification commands;
- explicit exclusions;
- common failure cases such as expired sessions, malformed responses and slug conflicts.

Do not document endpoints until verified from the backend implementation.

⸻

Error handling

Map backend failures into safe application-level categories.

Expected categories include:

- unauthenticated;
- forbidden;
- not found;
- validation;
- conflict;
- rate limited, if applicable;
- network;
- server;
- invalid response;
- unknown safe failure.

Raw response bodies, stack traces, SQL details and internal exception messages must not be rendered or logged.

A confirmed unauthenticated response must use the session-expiry mechanism added by PR 13A and return the administrator to login safely.

A 403 must not automatically be treated as logout unless the authentication contract explicitly defines it that way.

⸻

Idempotency and concurrency

- Repeated list and detail requests must be safe.
- Duplicate form submissions must be prevented while pending.
- Repeated activate/deactivate actions must converge on the server-confirmed state.
- Repeated delete attempts must handle an already-deleted Assistant safely.
- A late response from an earlier request must not overwrite a newer confirmed state.
- Cache invalidation must not cause mutation replay.
- No mutation should be automatically retried unless the backend operation is explicitly idempotent and the retry policy is justified.
- Use backend conflict responses rather than attempting to guarantee slug uniqueness in the browser.

⸻

Tests

Use Vitest, React Testing Library, userEvent and the network mocking approach established by PR 13A.

Cover:

API boundary

- exact paths, methods and payloads;
- credentials: 'include';
- cancellation;
- list and detail response validation;
- invalid enum values;
- malformed collections;
- malformed timestamps;
- safe error mapping;
- session-expiry notification;
- no automatic mutation retries.

List page

- loading;
- populated results;
- empty state;
- retryable error;
- status and visibility labels;
- navigation to create and edit;
- responsive action accessibility;
- pagination, search or filtering where supported.

Forms

- required name;
- slug validation;
- enum selection;
- editable suggested slug behaviour if implemented;
- duplicate-submission prevention;
- retained values after failure;
- successful create;
- successful update;
- slug conflict;
- backend validation errors;
- unsaved-change warning.

Status and deletion

- activate;
- deactivate confirmation;
- failed status change retains confirmed state;
- delete confirmation;
- successful deletion;
- dependency conflict;
- already-deleted response;
- focus restoration.

Routing

- authenticated access;
- expired-session handling;
- unknown Assistant;
- safe navigation after create and delete.

Do not test only mocked hooks. Exercise the feature through the HTTP boundary so request construction, response validation and cache behaviour are covered together.

⸻

Acceptance criteria

- The PR extends the merged PR 13A admin application.
- The Assistants placeholder is replaced by a functional list page.
- The implementation uses the real authenticated backend contract.
- No endpoint, field or backend capability is invented.
- Administrators can list existing assistants.
- Administrators can create an assistant using supported fields.
- Administrators can edit backend-supported fields.
- Status and visibility are displayed accessibly.
- Administrators can activate and deactivate assistants where permitted.
- Administrators can delete assistants where permitted.
- Destructive actions require confirmation.
- Slug validation and conflicts are handled safely.
- Loading, empty, error and not-found states are implemented.
- Malformed successful responses are rejected.
- Session expiry uses the existing authentication invalidation mechanism.
- Requests use credentials: 'include'.
- Components and pages do not call fetch directly.
- No credentials, cookies or raw backend errors are logged or displayed.
- Query caches remain consistent after create, update, status change and deletion.
- Duplicate submissions are prevented.
- The interface is keyboard accessible and usable at mobile widths.
- Storybook stories are deterministic and make no network requests.
- Tests cover API contracts and primary user workflows.
- Admin lint, type-check, tests, build and Storybook build pass.
- Existing backend, RAG UI and public Assistant widget behaviour remain unchanged.
- git diff --check passes.

⸻

Verification

Run the repository-standard commands discovered from the current root and apps/admin/package.json.

At minimum verify:

npm run lint:admin
npm run typecheck:admin
npm run test:admin
npm run build:admin
npm run build-storybook --workspace=apps/admin
git diff --check

Use the actual script names if they differ.

Also run the relevant existing frontend and backend checks required by AGENTS.md.

Before completion, manually verify:

1. Log in as an administrator.
2. Open the Assistants page.
3. Create a private inactive assistant.
4. Edit its name or other supported mutable field.
5. Activate it.
6. Change visibility if supported.
7. Refresh the page and confirm server persistence.
8. Deactivate it.
9. Delete it.
10. Confirm the list updates correctly.
11. Repeat a route with an expired session and confirm safe redirection.
12. Confirm no requests are made by Assistant Storybook stories.

Completion response

Summarise:

- files and feature areas changed;
- backend Assistant API contract used;
- routes added or replaced;
- tests added;
- commands run and their results;
- any backend limitations discovered.

Do not commit, push or create a pull request.
