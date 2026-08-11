# PR 13D — Assistant Behaviour, Prompts, Publishing & Preview

## Repository state

Expected branch:

`feature/13d-assistant-behaviour-publishing-preview`

Base branch:

`main`

PR 13D should be started only after the frontend prerequisites it depends on have landed on the selected base branch.

Dependencies:

* PR 13A — Admin Application Foundation
* PR 13B — Admin Assistant Management Foundation
* PR 13C — Assistant Knowledge & Retrieval Configuration
* Existing administrator authentication API
* Existing administrator Assistant management API
* Existing public Assistant chat API
* Backend Assistant behaviour/prompt/publishing contract, if implemented in a preceding backend PR

PR 13C is currently represented by PR #66 and is not yet merged at the time this specification was written.

Before making changes, inspect the actual repository state.

If PR 13C is not present on the selected base branch, or the required backend behaviour/publishing API does not exist, stop and report the repository-state mismatch.

Do not silently implement missing backend functionality as part of PR 13D.

Do not create browser-only configuration as a substitute for missing server persistence.

Do not invent API endpoints, request fields, response fields, publishing semantics, revision models, model controls, or prompt behavior that the backend does not expose.

### Read first

* AGENTS.md
* docs/architecture/repository-map.md
* docs/architecture/dependency-rules.md
* .codex/tasks/TEMPLATE.md
* relevant PR 13A specification
* relevant PR 13B specification
* relevant PR 13C specification
* apps/admin/README.md
* apps/admin/package.json
* apps/admin/src/App.tsx
* apps/admin/src/App.test.tsx
* apps/admin/src/api/adminApi.ts
* apps/admin/src/api/adminApi.test.ts
* apps/admin/src/features/assistants/Assistants.tsx
* apps/admin/src/features/assistants/Assistants.stories.tsx
* PR 13C knowledge-source components once merged
* apps/admin/src/components/AdminShell.tsx
* apps/admin/src/styles.css
* apps/assistant/src/AssistantWidget.tsx
* apps/assistant/src/AssistantWidget.types.ts
* apps/assistant/src/publicChatClient.ts
* relevant Assistant backend administrator schemas/routes
* relevant public Assistant chat routes
* backend tests defining Assistant publication and behaviour semantics

### Primary change area

Expected primary change surface:

apps/admin/src/features/assistants/
apps/admin/src/api/adminApi.ts
apps/admin/src/api/adminApi.test.ts
apps/admin/src/App.tsx
apps/admin/src/App.test.tsx
apps/admin/src/styles.css
apps/admin/README.md

A small dependency or adapter around the existing Assistant widget may also be required for preview.

Prefer reusing the existing widget package/component instead of copying its conversation UI into the admin application.

### Excluded areas

Unless repository inspection proves they are explicitly required by an already-existing contract, do not modify:

* ingestion architecture;
* retrieval implementation;
* embedding generation;
* vector persistence;
* public widget visual design;
* widget npm release automation;
* administrator authentication;
* knowledge-source domain behavior;
* model/provider selection;
* temperature;
* top-p;
* token limits;
* arbitrary LLM generation parameters;
* analytics;
* evaluation dashboards;
* audit-log UI;
* multi-user approval workflows;
* version-history UI;
* scheduled publishing;
* A/B testing;
* widget branding;
* CSS theme customization.

⸻

## Objective

Add the administrator experience for configuring how an Assistant behaves, managing the prompts and user-facing conversation text supported by the backend, controlling publication safely, and previewing the resulting Assistant before making it publicly available.

The administrator must be able to answer four practical questions from one coherent Assistant editing workflow:

1. How should this Assistant behave?
2. What prompt and conversation text will it use?
3. What version/configuration is currently public?
4. What will users experience if I publish these changes?

The implementation must use the backend as the source of truth.

Editing configuration must not immediately and accidentally change a production Assistant unless that is the explicit backend publishing model.

Preview must allow administrators to test unpublished configuration when the backend explicitly supports such preview semantics.

⸻

## Current architecture

The administrator application currently has:

* authenticated protected routes;
* an Assistant list;
* Assistant creation;
* Assistant editing;
* activation/deactivation;
* public/private visibility;
* typed API response validation;
* safe administrator error handling;
* unsaved-change protection;
* Storybook;
* rendered workflow tests;
* API-boundary tests.

Assistant management currently focuses on identity and lifecycle.

The public Assistant widget already has a reusable conversation surface accepting:

* Assistant identifier;
* API base URL;
* Assistant name;
* welcome message;
* input placeholder;
* suggested questions.

The public widget must remain the canonical user-facing conversation implementation.

PR 13D must therefore avoid building a separate approximate preview component whose behavior can drift from the real widget.

Where practical, preview should render the actual Assistant widget or its existing underlying conversation component with an appropriate preview chat adapter.

⸻

## Required implementation

### 1. Extend Assistant administration into a structured editor

Do not continue growing AssistantFormPage into one very large form.

Refactor the Assistant editing experience into clear sections or subroutes if necessary.

A suitable structure is:

Assistant
├── General
├── Behaviour
├── Knowledge
├── Preview
└── Publishing

Exact presentation may use tabs, secondary navigation, or clearly separated sections consistent with the existing application.

Do not introduce a heavyweight admin framework merely for navigation.

Existing Assistant identity management must continue working.

If PR 13C already introduces an Assistant-scoped management route such as:

/admin/assistants/:assistantId/knowledge

preserve that route hierarchy and add Behaviour/Preview routes consistently.

Suitable routes may be:

/admin/assistants/:assistantId/edit
/admin/assistants/:assistantId/behaviour
/admin/assistants/:assistantId/knowledge
/admin/assistants/:assistantId/preview

Publishing may live within Behaviour or have its own route depending on the verified backend contract.

Avoid having two separate places mutate the same setting.

⸻

### 2. Behaviour configuration

Expose only behavior fields actually supported by the backend.

Expected categories may include, where present in the verified API:

* system/instruction prompt;
* welcome message;
* input placeholder;
* suggested questions;
* fallback or uncertainty guidance;
* response-style instructions;
* other explicitly supported Assistant behavior text.

Do not invent numerical model controls.

The system prompt/instruction field should be clearly distinguished from user-facing copy.

For example:

Instructions

Describe how the Assistant should answer, what role it performs, what it should avoid claiming, and any domain-specific response guidance.

Welcome message

The text displayed before the user sends the first message.

Suggested questions

Optional starting questions displayed to the user.

Input placeholder

Short guidance displayed in the conversation input.

Use labels that describe effects rather than internal implementation details wherever possible.

⸻

### 3. Prompt editing

For long instruction fields:

* use a multiline text area;
* preserve whitespace exactly according to the backend contract;
* do not silently trim meaningful prompt content;
* show any backend-supported maximum length;
* expose character count when useful;
* provide accessible validation;
* retain unsaved text when validation fails.

Do not implement a rich-text editor.

Do not implement markdown rendering unless the backend explicitly defines prompts as markdown and the editor benefits materially from it.

Do not add syntax highlighting.

Prompt content must never be:

* logged;
* inserted into route URLs;
* placed in analytics;
* stored in local storage;
* stored in session storage;
* exposed through generic error messages.

Raw backend exceptions must remain hidden.

⸻

### 4. Suggested questions

If suggested questions are supported, provide a small ordered editor.

Required behavior:

* add a question;
* edit a question;
* remove a question;
* preserve explicit ordering;
* prevent empty questions;
* enforce backend count/length limits;
* prevent accidental duplicate submission.

Use normal React state.

Do not add a drag-and-drop library solely for ordering a handful of questions unless an existing project dependency already provides the capability and it meaningfully improves accessibility.

Simple Move up / Move down controls are acceptable and easier to test.

⸻

### 5. Draft versus published state

Inspect the backend publishing model before implementing UI.

The UI must represent the verified server semantics exactly.

Possible backend designs include:

* editable draft plus separate published configuration;
* revision records;
* a publish timestamp/version;
* direct configuration updates plus an explicit publish operation.

Do not assume which model exists.

If the backend provides draft/published state, the page must clearly communicate:

* whether unpublished changes exist;
* when the current public configuration was published, if available;
* whether the Assistant has never been published;
* whether a publication request is currently pending;
* whether the Assistant is publicly reachable.

Do not infer “published” solely from status === active.

Do not infer “published” solely from visibility === public.

Those lifecycle fields may control availability but are not automatically equivalent to configuration publication.

⸻

### 6. Save draft

Where supported, provide an explicit Save changes or Save draft operation.

Saving must:

* prevent duplicate submissions;
* use concurrency protection exposed by the backend;
* use server-confirmed results as authoritative;
* show accessible success feedback;
* preserve user input after recoverable validation/network failures;
* detect stale edits;
* prevent an older request from overwriting newer confirmed state.

If the backend returns a concurrency token/version, always send the expected token for mutations that require it.

On stale-write conflict:

* do not automatically overwrite;
* explain that configuration changed elsewhere;
* offer a safe refresh/reload action;
* warn before discarding local unsaved work.

Do not implement automatic mutation retries.

⸻

### 7. Unsaved-change protection

Extend the existing unsaved Assistant-form navigation protection to Behaviour editing.

The warning should activate when any editable configuration differs from the last confirmed server state.

Cover:

* route navigation;
* browser refresh;
* closing the page;
* navigation to Preview;
* navigation to Knowledge;
* navigation back to Assistant list.

Do not block navigation after a confirmed successful save when local state equals the returned server representation.

⸻

### 8. Publishing workflow

Provide an explicit publish action only when the backend supports publication.

Publishing must never occur implicitly merely because:

* the Assistant form was saved;
* Preview was opened;
* status changed;
* visibility changed.

Before publication, show a confirmation dialog summarising the effect.

At minimum the dialog must identify:

* the Assistant being published;
* that saved draft configuration will become the public configuration;
* whether publication alone makes the Assistant available or whether active/public lifecycle state is separately required.

Use the actual backend semantics for that final point.

The confirmation must not dump the complete system prompt.

A concise statement is sufficient.

While publishing:

* disable duplicate publish actions;
* prevent conflicting mutations;
* announce pending state accessibly.

After publishing:

* reconcile the page with the returned authoritative state;
* display a clear success notice;
* update published-version/time information if supplied;
* ensure the UI no longer falsely shows a dirty draft when the server says draft and published configuration match.

⸻

### 9. Unpublish or publication reversal

Do not invent an “Unpublish” action.

If the backend explicitly supports unpublishing, expose it with a destructive confirmation and clearly describe its public effect.

If public availability is instead controlled by existing status and visibility, keep using those established controls rather than creating a second competing availability mechanism.

The UI must make this distinction understandable.

⸻

### 10. Preview

Preview is a major requirement of this PR.

Administrators must be able to inspect the user experience before publication.

Reuse the existing Assistant widget/conversation implementation wherever possible.

Do not create a mock chat box that merely looks similar to the public widget.

Preview must show, as applicable:

* Assistant name;
* welcome message;
* suggested questions;
* placeholder;
* actual conversation rendering;
* actual loading state;
* actual assistant/user message layout;
* actual errors from the preview API mapped into safe user-facing states.

Preview semantics

Inspect the backend contract.

The preferred behavior is:

Preview saved draft configuration without publishing it.

That requires a backend preview endpoint or equivalent server-supported mechanism that applies the draft configuration while preserving normal retrieval and generation behavior.

If such a contract does not exist, stop and report the repository-state mismatch.

Do not fake prompt preview by passing unpublished prompt text only to the frontend because system instructions must be applied server-side during generation.

Do not call the production public chat endpoint and label the result “draft preview” if that endpoint uses the published configuration.

If the only supported backend preview is for already-published assistants, label it accurately.

⸻

### 11. Preview conversation isolation

Administrator preview conversations must not contaminate public state or unrelated conversations.

Use the existing stateless/conversation contract appropriately.

Preview state should live only in component memory unless the backend defines a preview-session resource.

Resetting Preview should clear the local conversation.

Provide a clear Reset conversation control.

Do not store preview messages in local/session storage.

Do not place prompts, retrieved knowledge, or conversation contents in URLs.

Do not log conversation contents.

⸻

### 12. Preview configuration source

The Preview page must clearly indicate what is being previewed.

Examples depending on backend support:

* Previewing saved draft
* Previewing published configuration

If local Behaviour edits are unsaved, do not silently preview them unless the backend contract explicitly supports ephemeral preview payloads.

Prefer:

1. Administrator edits.
2. Administrator saves draft.
3. Preview uses server-confirmed draft.
4. Administrator publishes when satisfied.

This creates a deterministic workflow and prevents the preview from representing configuration that has never reached the server.

⸻

### 13. Reuse the public widget

Investigate the cleanest reuse path.

The admin package currently does not depend on the Assistant widget package.

Prefer one of these approaches, in order:

1. Import/reuse the public AssistantWidget package directly if workspace dependency architecture allows it cleanly.
2. Reuse the existing underlying conversation component through an intentionally public/shared boundary if that avoids coupling preview to the production public API client.
3. Extract only genuinely shared presentation code to a small package/shared module if repository dependency rules require it.

Do not copy/paste widget JSX and CSS into apps/admin.

Do not create circular dependencies.

Do not make the publishable Assistant widget depend on the admin application.

The dependency direction must remain:

shared/widget component
        ↑
        │
public widget     admin preview

not:

admin → public app internals → admin

Follow docs/architecture/dependency-rules.md.

⸻

### 14. Preview adapter

The existing public AssistantWidget constructs a public chat client from apiBaseUrl and assistantId.

If backend draft preview uses a different administrator endpoint, introduce the smallest abstraction necessary to inject the appropriate chat client.

For example, the underlying conversation component may accept a chatClient interface.

The public package can continue constructing its public client exactly as it does today.

Admin Preview can provide an authenticated preview client implementing the same interface.

Do not weaken or replace the existing public API contract.

Do not expose administrator credentials to the widget.

Administrator preview requests must use the existing HTTP-only administrator session through the admin API boundary.

⸻

### 15. Safe error handling

Handle:

* unauthenticated;
* forbidden;
* assistant not found;
* draft not found if applicable;
* validation failure;
* stale/concurrency conflict;
* publish conflict;
* preview unavailable;
* network failure;
* server failure;
* malformed successful response.

401 should continue to invalidate the administrator session using the existing authentication behavior.

403 must preserve the session and display a permission error.

Raw prompt text, provider errors, generation payloads, stack traces, or internal preview request bodies must never be shown.

⸻

### 16. Loading and pending states

Every server-backed area must distinguish:

* initial loading;
* loaded;
* save pending;
* publish pending;
* preview-message pending;
* retryable load error.

Do not use one global “loading” flag for the entire Assistant editor.

A preview response should not disable navigation across the whole admin application.

A save or publish mutation should disable only conflicting actions.

⸻

### 17. Accessibility

Maintain the accessibility expectations established by PR 13A–13C.

Required:

* semantic form labels;
* accessible validation summaries;
* keyboard-operable tabs/navigation if used;
* visible keyboard focus;
* native buttons for actions;
* native dialog behavior for confirmations;
* deterministic focus restoration;
* status announcements for save/publish success;
* pending state announcements;
* no color-only publication indicators;
* suggested-question controls with descriptive accessible names.

After successful publish, move focus to or announce the success region.

After cancelled publication, restore focus to the Publish button.

⸻

### 18. Styling

Use the existing admin visual language.

Do not introduce a new design system.

The Behaviour editor should remain readable at long prompt lengths.

Recommended layout:

┌───────────────────────────────────────────────┐
│ Redmoor Assistant                            │
│ General  Behaviour  Knowledge  Preview       │
├───────────────────────────────────────────────┤
│ Behaviour                                    │
│                                               │
│ Instructions                                 │
│ ┌───────────────────────────────────────────┐ │
│ │                                           │ │
│ │                                           │ │
│ └───────────────────────────────────────────┘ │
│                                               │
│ Welcome message                              │
│ [.........................................]  │
│                                               │
│ Suggested questions                          │
│ 1. [..............................]  Remove  │
│ 2. [..............................]  Remove  │
│ [+ Add question]                             │
│                                               │
│                         [Save draft]         │
└───────────────────────────────────────────────┘

Preview may use a two-column layout on large screens:

Behaviour summary | Assistant preview

but must stack cleanly on narrow screens.

Do not reduce widget fidelity merely to fit a side panel.

⸻

## Storybook

Add deterministic stories for the new feature.

At minimum include:

* Behaviour loaded;
* unsaved Behaviour edits;
* validation error;
* save pending;
* save success;
* stale-update conflict;
* unpublished draft;
* published configuration;
* draft changes awaiting publication;
* publish confirmation;
* publish pending;
* publish success;
* preview initial state;
* preview conversation;
* preview request pending;
* preview safe failure.

Use fictional fixed data.

No Storybook story may:

* call a live backend;
* depend on authentication cookies;
* depend on current time;
* use random identifiers;
* mutate shared state between stories.

⸻

## API boundary

Extend the existing AdminApi rather than introducing a separate ad-hoc fetch layer.

Use the precise existing backend routes.

Expected conceptual operations may include:

getAssistantBehaviour(...)
updateAssistantBehaviour(...)
publishAssistant(...)
previewAssistantMessage(...)

These are examples only.

Use the actual endpoint names and payload shapes discovered in the backend.

Runtime-validate all successful responses at the API boundary.

Validate:

* IDs;
* timestamps;
* enums;
* optional/null fields;
* revisions;
* concurrency tokens;
* bounded arrays;
* suggested-question fields;
* publication metadata.

Reject malformed successful responses with AdminApiError('invalid_response').

Do not leak response bodies through thrown messages.

⸻

## Tests to add or update

### `apps/admin/src/api/adminApi.test.ts`

Cover the verified behavior/publishing contracts.

At minimum:

* exact GET behavior-config request;
* exact update request body;
* credentials included;
* concurrency token forwarded;
* prompt whitespace preserved;
* welcome message preserved;
* suggested-question ordering preserved;
* malformed behavior response rejected;
* malformed publication metadata rejected;
* unsupported enum rejected;
* invalid timestamp rejected;
* stale conflict safely mapped;
* validation errors safely mapped;
* 401 mapping;
* 403 mapping;
* 404 mapping;
* publish request contract;
* publish response validation;
* preview request contract;
* preview response validation;
* cancellation forwarding for reads;
* raw backend failures discarded.

Where optional fields exist, test null/omitted semantics explicitly.

⸻

### `apps/admin/src/App.test.tsx`

Add rendered workflow coverage.

Routing

* authenticated Behaviour route;
* authenticated Preview route;
* Assistant not found;
* unauthenticated redirect;
* expired session;
* forbidden response.

Behaviour

* load server configuration;
* render existing instructions;
* edit instructions;
* preserve multiline whitespace;
* edit welcome message;
* add suggested question;
* edit suggested question;
* remove suggested question;
* reorder suggested questions;
* validation failure retains all values;
* duplicate save prevented;
* save sends exact payload;
* successful save reconciles from response;
* stale conflict does not overwrite local changes;
* retryable network failure retains values;
* unsaved navigation warning;
* unload warning;
* save clears dirty state.

Publishing

* unpublished state;
* published state;
* unpublished changes indicator;
* confirmation required;
* cancel restores focus;
* duplicate publication blocked;
* successful publication reconciles state;
* publish failure retains saved draft;
* stale publication conflict handled safely;
* availability text matches status/visibility semantics.

Preview

* preview renders canonical widget/conversation UI;
* welcome message displayed;
* suggested questions displayed;
* placeholder displayed;
* user can send a preview message;
* pending response visible;
* returned assistant message rendered;
* multi-turn conversation works;
* reset clears conversation;
* safe preview error;
* draft/published source is labelled accurately;
* preview does not write to browser storage;
* prompt text does not enter route URLs;
* 401 expires admin session;
* public widget behavior outside admin remains unchanged.

Use semantic queries and observable outcomes.

Do not assert only internal component state.

⸻

## Public widget regression

Because Preview should reuse the public Assistant widget implementation, explicitly protect the published package.

Run and preserve:

* Assistant widget public API tests;
* public chat client tests;
* widget conversation tests;
* package build;
* package type declarations;
* package export surface.

Do not introduce a breaking public-package API merely for admin preview.

If a new injection point is required, make it additive or keep it internal where possible.

⸻

## Security and privacy

PR 13D handles some of the most sensitive administrator-authored configuration.

Never log:

* system prompts;
* Assistant instructions;
* preview conversations;
* retrieved chunks;
* source text;
* cookies;
* authorization data;
* request bodies containing prompts.

Do not persist these values in browser storage.

Do not expose them in URLs.

Do not include them in generic telemetry.

Do not display raw backend/provider failures.

Public chat endpoints must continue to expose only behavior intended for public users.

Administrator-only draft prompts must not become retrievable through public Assistant metadata endpoints unless the backend explicitly intends that.

⸻

## Idempotency and concurrency

Do not add idempotency machinery where the backend operation is already naturally protected by revision/concurrency semantics.

For draft updates:

* use the backend concurrency token/version if required;
* prevent duplicate UI submissions;
* reject stale writes rather than blindly replacing server state.

For publish operations:

* inspect whether the backend provides an idempotency key, expected draft revision, or concurrency token;
* follow that contract exactly;
* repeated publication submission from the UI must not cause multiple conflicting operations;
* do not manufacture a client-side publishing state that can diverge from the server.

Preview messages are independent conversation operations unless the backend defines explicit message idempotency.

Do not reuse mutation idempotency keys across unrelated Assistant operations.

⸻

## Documentation

Update apps/admin/README.md with:

* Behaviour page purpose;
* supported configuration;
* save versus publish distinction;
* preview semantics;
* which configuration Preview uses;
* requirement for the backend preview contract;
* interaction between publication and Assistant status/visibility;
* unsaved-change behavior;
* security note that prompts/conversations are not stored in browser storage.

Do not document unsupported future controls.

⸻

## Acceptance criteria

* PR 13D refuses to proceed if the required backend behaviour/publishing/preview contract is absent.
* No frontend-only persistence is introduced.
* Existing Assistant identity/status/visibility editing continues to work.
* Behaviour configuration is loaded from the backend.
* Administrators can edit every behavior field supported by the verified backend contract.
* System instructions are clearly separated from user-facing copy.
* Prompt whitespace and ordering semantics are preserved.
* Suggested questions can be managed accessibly when supported.
* Saving configuration uses authoritative server responses.
* Concurrency/stale-update conflicts cannot silently overwrite another administrator’s changes.
* Unsaved-change protection covers Behavior editing.
* Saving does not implicitly publish unless the verified backend explicitly defines that semantic.
* Publishing requires deliberate administrator action where supported.
* Publish confirmation accurately describes its effect.
* Publication state is not incorrectly inferred from active/public alone.
* Successful publication reconciles authoritative server state.
* Preview clearly identifies whether it uses draft or published configuration.
* Draft Preview uses a real backend-supported preview path.
* The frontend never labels public-chat execution as draft preview when it is not.
* Preview uses the canonical Assistant widget/conversation implementation rather than a copied imitation.
* Preview supports real multi-turn administrator testing.
* Preview conversations can be reset.
* Preview messages and prompts are not stored in browser storage or URLs.
* Administrator preview requests remain authenticated through the admin boundary.
* Public Assistant widget API behavior remains backwards compatible.
* 401 expires the administrator session.
* 403 preserves the session.
* Malformed successful responses are rejected safely.
* Raw backend/provider errors are not exposed.
* Save/publish buttons prevent duplicate mutation submissions.
* Focus is restored deterministically after publication dialogs.
* Pending and successful operations are announced accessibly.
* Responsive behavior works at narrow viewport widths.
* Storybook covers deterministic Behaviour, publication, and Preview states.
* Existing PR 13A, 13B, and 13C functionality remains passing.
* Existing public widget tests remain passing.
* Admin lint passes.
* Admin type checking passes.
* Admin tests pass.
* Admin production build succeeds.
* Admin Storybook build succeeds.
* Assistant widget tests/build pass.
* git diff --check passes.

⸻

## Verification commands

Run from the repository root.

Use actual scripts present on the branch if names have changed.

```bash
git status -sb
# Focused admin tests
npm test --workspace @ai-discovery-assistant/admin -- src/api/adminApi.test.ts
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx
# Complete admin verification
npm run test:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run lint:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
# Public Assistant widget regression
npm run test --workspace @redmoor/assistant-widget
npm run typecheck --workspace @redmoor/assistant-widget
npm run lint --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
git diff --check
git status -sb
```

If the workspace does not expose one of the exact commands above, inspect package.json and run the equivalent existing script rather than adding a duplicate script solely to satisfy this specification.

Also run the focused backend contract tests covering:

* Assistant behavior configuration;
* publication;
* administrator preview;
* public Assistant availability;

without changing backend production behavior.

⸻

## Manual verification

Where a local backend and administrator session are available:

1. Open an existing Assistant.
2. Navigate to Behaviour.
3. Change its instructions and welcome message.
4. Save the draft.
5. Confirm refreshing the page returns the saved values.
6. Confirm the public Assistant has not changed before publication, if the backend supports separate draft/public configuration.
7. Open Preview.
8. Confirm Preview identifies the configuration source accurately.
9. Send a question that visibly exercises the changed instructions.
10. Send a follow-up question and confirm conversation context works.
11. Reset Preview and confirm the conversation clears.
12. Publish the saved configuration.
13. Confirm publication success is reflected by authoritative server state.
14. Open the normal public widget.
15. Confirm it now exhibits the published behavior.
16. Modify the draft again and confirm the public widget remains on the previous published configuration until another publish.
17. Confirm changing status/visibility behaves according to the existing Assistant lifecycle rules.
18. Confirm no prompt text or preview conversation appears in browser local storage, session storage, or route URLs.

Do not claim manual verification was completed unless it was actually performed.

⸻

## Completion rule

The task is complete only when the administrator can reliably:

configure behaviour
        ↓
save server-backed draft/configuration
        ↓
preview the real Assistant behavior
        ↓
publish deliberately
        ↓
observe authoritative published state

without duplicating the public widget, inventing backend semantics, leaking prompt content, bypassing concurrency controls, or regressing the existing Assistant, knowledge, authentication, or public chat functionality.
