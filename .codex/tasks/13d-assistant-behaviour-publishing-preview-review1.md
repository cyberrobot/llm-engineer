# PR 13D Review Fixes — Streaming Preview and Spec Compliance

## Repository state

Expected branch:

`feature/13d-assistant-behaviour-publishing-preview`

Base branch:

`main`

Worktree:

Use the existing frontend worktree containing PR #71.

Do not create a new branch.

Do not reimplement completed PR 13D functionality.

Dependencies:

* PR 11G Assistant Behaviour, Publishing & Preview backend API is implemented
* Admin application foundation exists
* Administrator Assistant management exists
* Assistant knowledge-management UI exists
* @redmoor/assistant-widget exists and is already used by the admin preview implementation
* PR #71 already implements the main Behaviour, publishing and Preview UI

### Read first

* AGENTS.md
* relevant frontend AGENTS.md files
* docs/architecture/repository-map.md
* docs/architecture/dependency-rules.md
* .codex/tasks/TEMPLATE.md
* .codex/tasks/11g-assistant-behaviour-publishing-preview.md
* PR #71 current diff
* apps/admin/src/api/adminApi.ts
* apps/admin/src/features/assistants/AssistantBehaviour.tsx
* apps/admin/src/App.test.tsx
* apps/admin/src/api/adminApi.test.ts
* apps/assistant/src/index.ts
* apps/assistant/src/components/assistant-widget/AssistantWidget.tsx
* apps/assistant/src/components/assistant-widget/AssistantWidget.types.ts
* relevant Assistant widget tests
* apps/admin/package.json
* apps/assistant/package.json

### Primary change area

* apps/admin/src/api/
* apps/admin/src/features/assistants/
* apps/assistant/src/components/assistant-widget/
* apps/assistant/src/index.ts
* relevant tests and documentation

### Canonical implementation examples

Use the existing public Assistant chat implementation as the canonical example for:

* SSE parsing
* incremental delta handling
* start / delta / complete / error event semantics
* request cancellation
* stream cleanup
* malformed event handling
* conversation state
* retry/error behaviour

Reuse existing parsing and streaming infrastructure where practical.

Do not create a second independent SSE implementation if the existing Assistant widget or API layer already contains suitable reusable logic.

Prefer extracting or extending existing abstractions over duplicating them.

### Relevant symbols

Current relevant symbols include:

* AssistantChatClient
* AssistantChatResponse
* AssistantChatError
* AssistantWidgetConversation
* previewAssistantMessage
* AssistantPreviewPage
* previewAnswerFrom

Exact names may change if refactoring produces a cleaner shared streaming API.

### Expected change surface

Expected changes should primarily involve:

* the reusable Assistant chat client contract;
* the reusable conversation renderer if required for incremental assistant output;
* admin preview API integration;
* admin preview tests;
* Assistant widget tests;
* exports needed by the admin application;
* documentation describing streaming preview behaviour.

Small supporting changes are acceptable where required.

### Excluded areas

Do not change:

* backend API contracts;
* Assistant behaviour persistence;
* behaviour draft/publish semantics;
* Assistant lifecycle semantics;
* knowledge ingestion;
* retrieval configuration;
* AI provider behaviour;
* public Assistant API routes;
* authentication architecture;
* admin Assistant identity management;
* unrelated knowledge-source UI;
* package release/version automation.

Do not introduce:

* WebSockets;
* polling;
* browser-side LLM execution;
* simulated streaming from a completed response;
* another admin-specific chat renderer;
* another complete SSE parser if one can be shared;
* arbitrary prompt preview requests.

### Unknowns Codex must verify

Before implementation, verify:

1. how the current public Assistant client consumes its SSE stream;
2. whether a reusable SSE parser already exists;
3. whether AssistantWidgetConversation currently supports incremental assistant message updates;
4. whether changing AssistantChatClient would break existing public consumers;
5. whether a backwards-compatible streaming extension is preferable to replacing the current send() contract;
6. whether the admin package should consume the workspace source directly or the package export for the shared streaming abstraction.

Do not make an unnecessary breaking change to the published widget API.

⸻

## Objective

Fix the remaining PR #71 review issues without regressing the completed PR 13D functionality.

The primary defect is that administrator Preview currently requests an SSE response but buffers the entire response using response.text() before displaying the Assistant answer.

The corrected flow must be:

Administrator sends preview message

↓

Authenticated preview request opens SSE response

↓

start event is validated

↓

each delta is consumed incrementally

↓

the Assistant response becomes visible incrementally in the canonical conversation UI

↓

complete finalises the message

or

↓

error terminates the request using the existing safe error model

The Preview experience must therefore exercise the backend streaming contract rather than converting it into a conventional buffered HTTP request.

The change must retain all existing behaviour already implemented by PR #71.

⸻

## Current architecture

PR #71 introduces administrator Behaviour and Preview functionality.

The Behaviour workflow already supports:

* loading the authoritative saved draft;
* editing instructions;
* editing welcome text;
* editing input placeholder;
* ordered suggested questions;
* optimistic concurrency;
* unsaved-change protection;
* explicit publication;
* publication confirmation;
* separate Assistant lifecycle controls.

The Preview workflow already:

* uses the saved draft;
* retrieves the current draft metadata;
* uses AssistantWidgetConversation;
* sends conversation history to the authenticated backend preview endpoint;
* supports multi-turn conversation;
* supports conversation reset;
* does not publish configuration;
* does not require the Assistant to be active/public.

However, the admin API currently does effectively:

await response.text()

and only then parses the collected SSE events.

This means Preview is not actually streamed.

The backend preview API already exposes the normal Assistant SSE protocol and should remain authoritative.

⸻

## Required implementation

### 1. Make the reusable chat client streaming-capable

Extend the existing reusable Assistant conversation/client architecture so a chat request may emit response content incrementally.

Use an API appropriate to the existing architecture.

Possible approaches include:

send(request, {
  signal,
  onDelta,
})

or:

stream(request, {
  signal,
  onStart,
  onDelta,
  onComplete,
})

or an async iterable abstraction.

Choose the smallest clean abstraction compatible with the existing public widget.

Do not create an admin-only streaming API if the behaviour is generic Assistant chat behaviour.

The abstraction must support:

* cancellation using AbortSignal;
* ordered deltas;
* deterministic completion;
* safe failure;
* exactly one logical assistant message per request.

Avoid speculative abstractions beyond what public chat and admin preview require.

⸻

### 2. Reuse the canonical SSE parser

Inspect the existing public Assistant API/client implementation.

If SSE parsing already exists:

* extract it if necessary;
* reuse it for Preview;
* keep protocol validation in one place.

The parser must understand the backend protocol:

* start
* delta
* complete
* error

Do not treat an arbitrary message event as successful protocol data unless the existing backend contract explicitly supports it.

Required validation includes:

* start occurs before deltas;
* duplicate invalid start events are rejected;
* delta events before start are rejected;
* events after completion are rejected or safely ignored according to the established parser contract;
* malformed JSON is rejected;
* malformed payload shape is rejected;
* unknown event types are rejected;
* error terminates the stream;
* premature EOF without complete is treated as an invalid/incomplete response.

Do not log preview message content or Assistant output while handling parser failures.

⸻

### 3. Remove buffered Preview handling

Remove the current behaviour whereby Preview waits for:

await response.text()

before producing an Assistant answer.

previewAnswerFrom() should either:

* be removed; or
* be replaced/refactored into a genuinely streaming parser used by the shared client infrastructure.

Do not retain a buffered fallback for normal successful Preview requests.

⸻

### 4. Render deltas incrementally

Update AssistantWidgetConversation or its reusable internal state management so the currently generating Assistant message can grow as SSE deltas arrive.

Expected user-visible behaviour:

delta: "Redmoor "

renders:

Redmoor

then:

delta: "helps businesses "

renders:

Redmoor helps businesses

without waiting for the complete event.

The final message after completion must exactly equal the concatenated delta stream.

Do not create one message bubble per delta.

There must be one Assistant message whose content is incrementally updated.

⸻

### 5. Preserve conversation-history semantics

A partially generated response must not be included as completed conversation history for a subsequent request.

Only a successfully completed Assistant response should become normal prior history.

Existing history limits must remain enforced.

Do not change the backend request history schema.

⸻

### 6. Preserve request cancellation

The existing Preview UI supports reset and component lifecycle cancellation through AbortSignal.

Ensure cancellation terminates:

* the fetch request;
* response stream reading;
* parser processing;
* pending UI state.

After abort:

* no further deltas may update the component;
* the request must not produce a generic server-error message;
* the component must not produce React state updates after unmount/reset.

Reset conversation must remain safe while generation is active.

⸻

### 7. Handle mid-stream failures correctly

If the stream fails after some deltas have already arrived:

* stop generation;
* do not treat the partial content as a completed Assistant response;
* surface the existing safe widget error state;
* allow retry where the existing error model considers the failure retryable.

Do not expose raw backend errors or SSE payloads.

Do not retain corrupted partial content as authoritative conversation history.

The UI may keep or remove partial visual output according to the existing widget pattern, but the behaviour must be deterministic and covered by tests.

⸻

### 8. Preserve PR 13D Behaviour functionality

Do not regress the existing behaviour editor.

The following must continue working:

* server-backed saved drafts;
* exact prompt whitespace preservation;
* welcome message editing;
* input placeholder editing;
* ordered suggested questions;
* question add/remove/reorder;
* frontend validation;
* stale-update 409 handling;
* preservation of local edits after conflicts;
* explicit refresh;
* unsaved navigation warning;
* explicit publication;
* exact draft revision publication;
* publication confirmation;
* publication disabled for dirty local state;
* inactive/private publication messaging.

Do not make Preview use unsaved local editor state.

Preview must continue using the server-authoritative saved draft only.

⸻

### 9. Preserve Preview lifecycle semantics

Preview must continue to work for Assistants that are:

* inactive;
* private;
* inactive and private.

Preview must not:

* activate an Assistant;
* change visibility;
* publish behaviour;
* write drafts;
* use the public chat endpoint as fallback.

The UI should continue stating which saved draft revision is being previewed.

⸻

### 10. Keep the canonical Assistant conversation component

Continue using the reusable Assistant widget conversation surface.

Do not fork the UI into an admin-only implementation merely to support streaming.

Changes needed to support incremental responses should be made in the reusable conversation architecture.

Keep public-widget behaviour backwards compatible unless a change is explicitly required.

⸻

### 11. Public API compatibility

Because @redmoor/assistant-widget is a publishable package, treat its exported client types as public contracts.

If extending AssistantChatClient:

* prefer backwards-compatible additions;
* avoid breaking existing consumers;
* update exported types deliberately;
* update package tests;
* update README/API documentation if the external contract changes.

Do not casually rename or remove existing exports.

If a breaking change is genuinely unavoidable, stop and report it rather than silently changing the public package API.

⸻

### 12. Error mapping

Preserve the existing safe mapping between admin API errors and AssistantChatError.

At minimum retain appropriate handling for:

* unauthenticated;
* forbidden;
* not found;
* invalid request;
* conflict;
* network failure;
* malformed response;
* backend/server failure.

Session expiry must continue to use the existing authentication/session-expired path.

Do not expose raw backend detail, prompts, stack traces or response bodies.

⸻

### 13. Specification traceability

The repository currently does not contain:

.codex/tasks/13d-assistant-behaviour-publishing-preview.md

Do not invent a new authoritative 13D scope from scratch as part of the production implementation.

Use:

* PR #71 existing implementation;
* .codex/tasks/11g-assistant-behaviour-publishing-preview.md;
* existing 13A–13C conventions;
* the requirements in this remediation task

as the implementation contract for this fix.

If the actual original 13D task becomes available in the worktree, read it before implementation and verify the fix does not contradict it.

Report any material contradiction rather than silently choosing one requirement.

⸻

## Acceptance criteria

* Administrator Preview consumes the backend SSE response incrementally.
* Preview no longer waits for response.text() before displaying the generated answer.
* delta content becomes visible before the backend emits complete.
* One logical Assistant message is updated incrementally rather than creating one message per delta.
* The completed Assistant message exactly equals the ordered concatenation of received deltas.
* The reusable Assistant chat architecture is used rather than an admin-specific duplicate streaming implementation.
* Existing public widget consumers remain compatible.
* start, delta, complete and error events are validated safely.
* Invalid event order produces a safe invalid-response failure.
* Malformed JSON produces a safe invalid-response failure.
* Unknown SSE event types produce a safe invalid-response failure.
* EOF before a valid complete event is treated as incomplete/invalid.
* Backend error events do not become successful Assistant messages.
* Network errors remain safely mapped to the existing retryable error behaviour.
* Resetting the Preview while streaming aborts the active request.
* Navigating/unmounting while streaming aborts the active request.
* No deltas update the conversation after cancellation.
* A partial failed response is not included in subsequent completed conversation history.
* Multi-turn Preview continues to send completed prior user/Assistant history.
* Preview still uses the saved server draft rather than unsaved form values.
* Preview continues to work for inactive/private Assistants.
* Preview does not publish behaviour.
* Preview does not change Assistant status or visibility.
* Behaviour save semantics remain unchanged.
* Behaviour publish semantics remain unchanged.
* Optimistic concurrency handling remains unchanged.
* Unsaved Behaviour navigation protection remains functional.
* Publishing remains disabled while the Behaviour form has unsaved local changes.
* No preview prompt, conversation text or response content is persisted to local storage/session storage.
* No sensitive prompt or preview content is added to generic error logging.
* Existing admin tests continue passing.
* Existing Assistant widget tests continue passing.
* New streaming tests pass.
* Type checking passes.
* Production builds pass.

⸻

## Tests to add or update

### `apps/admin/src/api/adminApi.test.ts`

Add/update coverage for:

* Preview receives start;
* first delta is surfaced before complete;
* multiple deltas arrive in order;
* final completed answer is correct;
* malformed JSON;
* unknown event type;
* delta before start;
* duplicate start;
* complete before start;
* premature EOF;
* explicit backend error event;
* network interruption;
* request abort;
* no events processed after abort.

Prefer testing the shared SSE parser directly if it is extracted rather than duplicating all parser cases through the admin API façade.

### Assistant widget tests

Add tests proving:

* an Assistant message appears when generation starts as appropriate;
* streamed deltas update a single Assistant message;
* content is visible before stream completion;
* completion finalises the message;
* a failed partial response is not committed to conversation history;
* abort stops subsequent updates;
* reset during active generation cancels safely;
* retry behaviour remains correct.

### `apps/admin/src/App.test.tsx`

Update Preview workflow coverage to prove actual incremental rendering rather than a final resolved Promise only.

The test should explicitly control the stream.

Example sequence:

1. submit user message;
2. emit start;
3. emit first delta;
4. assert first partial content is visible;
5. verify request is still pending;
6. emit second delta;
7. assert combined partial content;
8. emit complete;
9. assert final conversation state.

Also retain coverage for:

* multi-turn history;
* Reset conversation;
* session expiry;
* inactive/private Assistants;
* Behaviour save;
* Behaviour conflict;
* publication confirmation;
* unsaved navigation warnings.

### Public widget regression tests

If the shared client contract changes, add regression tests proving existing non-preview/public usage remains functional.

⸻

## Verification commands

First inspect package scripts and use the repository’s canonical commands where they differ.

At minimum run the relevant equivalents of:

```bash

npm test --workspace apps/assistant
npm run typecheck --workspace apps/assistant
npm run build --workspace apps/assistant
npm test --workspace apps/admin
npm run typecheck --workspace apps/admin
npm run build --workspace apps/admin
```

If workspace script syntax differs, use the commands defined by the repository rather than changing package configuration solely to make these examples work.

Also run the repository-level frontend validation required by AGENTS.md.

Run the full relevant frontend test suite, not only newly added tests.

Do not report the task complete while any relevant test, typecheck or build command is failing.

⸻

## Completion report

When finished, report:

* the root cause of the buffered Preview behaviour;
* the shared streaming abstraction used or introduced;
* whether the public widget API changed;
* how cancellation is handled;
* how partial-stream failures are handled;
* tests added or updated;
* exact verification commands run;
* their results;
* any requirements that could not be verified because the original 13d-assistant-behaviour-publishing-preview.md task file remains absent.
