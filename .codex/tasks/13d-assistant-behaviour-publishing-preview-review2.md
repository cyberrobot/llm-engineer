# PR 13D Review Fixes — Storybook Streaming and Workflow Evidence

## Repository state

Expected branch:

`feature/13d-assistant-behaviour-publishing-preview`

Base branch:

`main`

Pull request:

`#71`

Dependencies:

- PR 13D implementation at commit `54c79ee` or later.
- `.codex/tasks/13d-assistant-behaviour-publishing-preview.md` remains authoritative.
- `.codex/tasks/13d-assistant-behaviour-publishing-preview-review1.md` remains authoritative for incremental Preview streaming.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/13d-assistant-behaviour-publishing-preview.md`
- `.codex/tasks/13d-assistant-behaviour-publishing-preview-review1.md`
- `apps/admin/src/features/assistants/AssistantBehaviour.stories.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/api/adminApi.test.ts`
- `apps/admin/src/features/assistants/AssistantBehaviour.tsx`
- `apps/assistant/src/components/assistant-widget/AssistantWidget.tsx`

### Primary change area

- `apps/admin/src/features/assistants/AssistantBehaviour.stories.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/api/adminApi.test.ts`

### Excluded areas

- Backend production behaviour.
- Assistant persistence or publication semantics.
- Public widget API redesign.
- New dependencies or Storybook frameworks.
- Unrelated PR 13A–13C behaviour.

---

## Objective

Close the remaining PR #71 review gaps by making the required Preview conversation story compatible with the canonical streaming client contract and by adding observable regression evidence for original PR 13D failure, concurrency, and navigation requirements.

## Current architecture

`AssistantWidgetConversation` prefers the optional streaming client method. A streaming client must surface each received delta through `onDelta` and return the same completed concatenation. The admin Preview production adapter satisfies this contract.

The deterministic Storybook `base.previewAssistantMessage` mock still returns only a final answer. Because the admin Preview adapter exposes it as a streaming client, the widget correctly rejects that inconsistent mock. Consequently, the required `PreviewConversation` story displays a safe failure rather than its expected Assistant response.

The Behaviour editor already contains guards for pending saves, network errors, unload protection, and publication conflicts. Several scenarios explicitly required by the original specification are not directly covered by rendered workflow tests.

## Required implementation

### 1. Repair the deterministic Preview conversation story

Update the Storybook preview API fixture to honor the streaming callback contract:

- emit the deterministic answer through `onDelta`;
- resolve with the exact same completed answer;
- do not introduce timers, randomness, live HTTP, cookies, or shared mutable state;
- preserve the separate pending and safe-failure stories.

The `PreviewConversation` play assertion must observe the completed fictional answer rather than a safe error.

### 2. Prove draft mutation failure and single-flight behaviour

Add rendered workflow coverage showing that:

- welcome-message edits and suggested-question removal are preserved in the exact save payload;
- an active draft save disables duplicate submission;
- a network failure retains all edited values;
- the safe error does not expose backend details;
- dirty Behaviour state prevents a cancelable `beforeunload` event.

Do not change the existing save implementation unless the new test reveals a defect.

### 3. Prove publication failure semantics

Add rendered workflow coverage for both retryable publication failure and stale publication conflict.

Verify that:

- the saved draft remains present;
- no successful publication state is fabricated;
- the publish action becomes available for an intentional retry;
- stale conflict uses the existing safe refresh guidance;
- raw backend content is not rendered.

### 4. Prove publication response validation

Add API-boundary coverage showing that malformed successful publication state is rejected with `AdminApiError('invalid_response')`.

Reuse the existing behaviour response validator. Do not add a second publication parser.

### 5. Preserve existing contracts

Do not alter:

- draft/published backend routes or payloads;
- concurrency tokens or exact draft revision publication;
- Preview streaming, cancellation, history, or safe-error behaviour;
- public widget compatibility;
- Assistant status or visibility semantics.

## Acceptance criteria

- The deterministic `PreviewConversation` story emits a delta and resolves with the same final answer.
- The Preview story no longer enters the invalid-response state.
- Duplicate draft saves remain blocked while a save is pending.
- Network save failure retains edited instructions, welcome message, and suggested questions.
- Dirty Behaviour state prevents `beforeunload` navigation.
- Publication network failure retains authoritative saved-draft state and permits retry.
- Stale publication conflict retains authoritative saved-draft state and presents safe refresh guidance.
- Malformed successful publication responses are rejected at the API boundary.
- Existing admin, widget, Storybook, backend-contract, type, lint, build, and package checks remain passing.

## Tests to add or update

### `apps/admin/src/App.test.tsx`

- pending duplicate draft save with exact edited payload;
- network save failure retains edited values;
- dirty Behaviour `beforeunload` protection;
- publication network failure retention;
- stale publication conflict retention and safe guidance.

### `apps/admin/src/api/adminApi.test.ts`

- malformed successful publication response maps to `invalid_response`.

### `apps/admin/src/features/assistants/AssistantBehaviour.stories.tsx`

- streaming-compatible deterministic Preview success fixture.

## Verification commands

```bash
npm test --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run lint --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
npm test --workspace @redmoor/assistant-widget
npm run typecheck --workspace @redmoor/assistant-widget
npm run lint --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
git diff --check
git status -sb
```

Also run the focused backend Assistant behaviour, publication, preview, and public-chat tests required by the governing specification without modifying backend production code.
