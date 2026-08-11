# PR 13D Review Fixes — Preview Permission Errors

## Repository state

Expected branch:

`feature/13d-assistant-behaviour-publishing-preview`

Base branch:

`main`

Pull request:

`#71`

Dependencies:

- `.codex/tasks/13d-assistant-behaviour-publishing-preview.md` remains authoritative.
- Review1 streaming and review2 workflow remediations are present at commit `53d1ef2` or later.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/13d-assistant-behaviour-publishing-preview.md`
- `apps/admin/src/features/assistants/AssistantBehaviour.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/assistant/src/components/assistant-widget/AssistantWidget.types.ts`

### Primary change area

- `apps/admin/src/features/assistants/AssistantBehaviour.tsx`
- `apps/admin/src/App.test.tsx`

### Excluded areas

- Public widget error-code or package-contract changes.
- Backend authorization behaviour.
- Authentication-session implementation.
- Behaviour, publication, or Preview transport payloads.

---

## Objective

Make Preview-message authorization failures satisfy the governing requirement that HTTP 403 preserves the administrator session and displays a safe permission error.

## Current architecture

Initial Behaviour and Preview workspace-load failures already render `AdminApiError('forbidden')` through the admin permission message.

During a Preview message, the admin adapter currently groups `forbidden` with not-found and conflict failures and maps all three to `AssistantChatError('assistant_unavailable')`. The canonical widget consequently renders “This assistant is currently unavailable,” which is safe but is not the required permission error.

The public widget error-code contract should not be widened solely for this admin-only presentation requirement.

## Required implementation

### 1. Preserve the administrator session

Do not call `sessionExpired()` for `AdminApiError('forbidden')`.

The administrator shell and authenticated route must remain mounted after the failed Preview message.

### 2. Render an admin-owned permission state

Handle Preview-message 403 within `AssistantPreviewPage` and replace the conversation surface with a safe admin permission alert.

The alert must:

- state that the administrator lacks permission to preview the Assistant;
- avoid raw backend details;
- use an accessible alert role;
- avoid persisting the question or error;
- prevent the canonical widget from simultaneously showing a misleading unavailable/server error.

Keep not-found, conflict, network, malformed-response, and server mappings unchanged.

### 3. Preserve the public widget contract

Do not add an admin-only error code to `AssistantChatErrorCode`.

Do not change public chat error wording or behavior.

### 4. Add rendered regression coverage

Add a Preview workflow test proving that a message-level forbidden response:

- displays the permission alert;
- does not redirect to login;
- preserves the authenticated administrator shell;
- does not display the generic unavailable error;
- does not expose raw details.

## Acceptance criteria

- Preview-message 403 preserves the authenticated session.
- Preview-message 403 displays a safe, explicit permission error.
- Preview-message 403 does not display the generic Assistant unavailable state.
- Initial workspace 403 behavior remains unchanged.
- Public widget API and error behavior remain unchanged.
- All required admin, widget, Storybook, backend-contract, and diff checks pass.

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
git diff --check
git status -sb
```

The backend is unchanged; retain the focused backend contract evidence from the PR review unless repository state changes.
