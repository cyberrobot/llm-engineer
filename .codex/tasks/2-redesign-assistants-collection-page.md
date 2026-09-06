# PR 2 — Redesign the Assistants collection page

## Repository state

Expected branch:

`feature/2-redesign-assistants-collection-page`

Base branch:

`main`

Worktree:

Current task worktree.

Dependencies:

- Existing Admin Assistants API and authentication.
- Existing `listAssistants` backend pagination/filter contract.
- Existing assistant update/delete mutation contracts.
- Existing Admin Storybook and Playwright visual-regression infrastructure.
- No backend or API contract changes are required.

### Read first

- `AGENTS.md`
- `apps/admin/AGENTS.md`
- `.codex/tasks/TEMPLATE.md`
- `apps/admin/src/features/assistants/Assistants.tsx`
- `apps/admin/src/features/assistants/Assistants.stories.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/styles.css`
- `apps/admin/e2e/admin-shell.spec.ts`
- `apps/admin/package.json`

### Primary change area

- `apps/admin/src/features/assistants/Assistants.tsx`
- `apps/admin/src/features/assistants/Assistants.stories.tsx`
- `apps/admin/src/styles.css`
- `apps/admin/src/App.test.tsx`

Expected additional visual-test surface:

- `apps/admin/e2e/assistants.spec.ts`
- corresponding Playwright screenshot baselines

### Canonical implementation examples

Use existing Admin patterns rather than introducing a separate component library or styling system:

- existing Admin page-introduction and card styling
- existing `Badge` treatment for assistant status and visibility
- existing `State` loading/error/empty behaviour
- existing `ActionDialog` mutation confirmation/error handling
- existing backend-offset pagination in `AssistantsPage`
- existing responsive table-to-card behaviour
- existing Storybook API fixtures and interaction tests
- `apps/admin/e2e/admin-shell.spec.ts` for deterministic Playwright visual regression

Keep Assistants-specific styling scoped to the Assistants collection page where practical so the redesign does not unintentionally restyle unrelated Admin tables.

### Relevant symbols

- `AssistantsPage`
- `Badge`
- `State`
- `ActionDialog`
- `Assistant`
- `AssistantStatus`
- `AssistantVisibility`
- `AdminApi.listAssistants`
- `AdminApi.updateAssistant`
- `AdminApi.deleteAssistant`
- `statusFilter`
- `visibilityFilter`
- `offset`
- `attempt`
- `page.total`
- `page.items`
- `assistant.concurrencyToken`

### Expected change surface

Primary:

- Assistants collection-page composition
- page introduction/actions
- collection summary metrics
- supported filters
- desktop table presentation
- responsive/mobile assistant cards
- assistant row-action menu
- selection/interaction styling
- Storybook collection states
- collection-page unit/integration tests
- collection-page Playwright visual regression coverage

Minor supporting changes may be made to reusable Assistants-local helpers when they simplify the implementation without changing unrelated pages.

### Excluded areas

Do not introduce or implement:

- search
- free-text filtering
- tags
- owners or ownership filtering
- analytics
- charts
- bulk selection
- bulk actions
- checkboxes for assistant selection
- duplication
- archive functionality
- archive filters or states
- new assistant lifecycle states
- sorting controls
- new backend endpoints
- new list query parameters
- client-side replacement for backend pagination
- changes to authentication/authorization
- unrelated Assistant create/edit/behaviour/publishing changes
- unrelated Admin page redesigns
- a new styling framework or design system

Do not change the backend Assistants API solely to support summary cards.

### Unknowns Codex must verify

Before implementation:

1. Verify the exact current Assistants list response contract and confirm that `total` is the authoritative backend count for the current request/filter set.
2. Verify no newer Assistants collection-page changes on the task branch supersede the implementation described by this spec.
3. Verify the current responsive table rules and ensure Assistants-specific changes do not regress unrelated Admin tables.
4. Verify the current Playwright snapshot naming/location convention before adding Assistants screenshots.
5. Verify whether an existing reusable action-menu primitive exists in the Admin application before implementing a local one.
6. Verify whether existing page/card styles can be reused before introducing Assistants-specific equivalents.

---

## Objective

Redesign the Admin Assistants collection page into a clearer operational management surface while preserving the existing backend contract and all existing assistant-management behaviour.

The page must provide:

- a redesigned introduction
- explicit Refresh and New Assistant actions
- useful collection summary cards
- only the currently supported status and visibility filters
- a more polished desktop table with assistant identity presentation
- accessible per-row actions
- clear row interaction/selection styling
- preserved backend pagination
- preserved mutation safety and error handling
- purpose-built mobile card presentation
- complete Storybook coverage for the principal collection states

This PR is a presentation and interaction redesign, not an expansion of Assistants product functionality.

## Current architecture

`AssistantsPage` owns the Assistants collection state and loads assistants through the established Admin API client.

The list request currently sends:

- `limit: 50`
- backend `offset`
- optional `status`
- optional `visibility`

The backend response provides:

- `items`
- `total`
- `limit`
- `offset`

Pagination is therefore backend-authoritative and must remain so.

Status and visibility are the only supported collection filters. Changing either filter resets the backend offset to zero and reloads the collection.

Assistant mutations already use the existing confirmation-dialog workflow:

- activate/deactivate calls `updateAssistant`
- status changes send the assistant concurrency token
- delete calls `deleteAssistant`
- conflicts and protected/dependent assistants have explicit error handling
- authentication expiry returns the user to the existing session-expired flow
- successful mutations reload the list
- deletion of the final item on a page returns to the valid preceding backend page
- completion notices receive focus for accessibility

The current desktop collection is a conventional table with separate Name and Slug columns and inline Edit / Activate / Deactivate / Delete actions.

Existing narrow-layout CSS converts table rows into stacked card-like rendering instead of requiring a wide horizontally scrolling table.

These behavioural contracts must survive the redesign.

## Required implementation

### 1. Redesign the page introduction

Replace the current minimal collection introduction with a deliberate Assistants management header.

The introduction must:

- clearly describe the purpose of the collection page
- fit the established Admin visual language
- retain the existing page-level heading hierarchy
- provide the two explicit page actions:
  - `Refresh`
  - `New Assistant`

Use `New Assistant` as the primary CTA and route it to:

`/admin/assistants/new`

Do not rename this CTA to `Create assistant`.

`Refresh` must be a button rather than navigation.

### 2. Add manual Refresh behaviour

Add an explicit `Refresh` action which re-fetches the currently displayed backend collection.

Refreshing must preserve:

- current `offset`
- current status filter
- current visibility filter

It must use the same `listAssistants` contract as ordinary collection loading.

Do not:

- silently reset pagination to page one
- clear active filters
- fetch every assistant client-side
- create a separate refresh API

Prevent accidental duplicate refresh submissions while a manual refresh is already pending.

Expose refresh progress accessibly, for example through the action's disabled/pending state and accessible text.

Existing list/session error handling must remain authoritative.

### 3. Add collection summary cards

After a successful list response, display summary cards for:

1. **Total**

   - Show the authoritative `page.total` value returned by the backend.
   - Never infer the authoritative total from `page.items.length`.
   - If backend filters affect `total`, display that returned filtered total as-is.

2. **Active**

   - Count assistants whose `status === "active"` in the currently loaded `page.items`.
   - This is explicitly a loaded-page metric, not a collection-wide metric.

3. **Public**

   - Count assistants whose `visibility === "public"` in the currently loaded `page.items`.

4. **Private**

   - Count assistants whose `visibility === "private"` in the currently loaded `page.items`.

5. **Most recently updated**
   - Determine the assistant with the latest valid `updatedAt` timestamp among currently loaded `page.items`.
   - Present enough information to identify the assistant and the update date/time.
   - Do not request additional backend data for this calculation.

For an empty loaded collection:

- total = `0`
- active = `0`
- public = `0`
- private = `0`
- most recently updated displays an intentional empty value such as `—`

The UI must make it clear through labels/supporting copy where appropriate that Active/Public/Private/Most recently updated describe the loaded page rather than falsely presenting these values as backend-wide totals.

### 4. Keep only supported filters

Retain exactly:

- Status
- Visibility

Status options remain:

- All statuses
- Active
- Inactive

Visibility options remain:

- All visibilities
- Public
- Private

Filter changes must continue to:

- reset `offset` to zero
- issue the backend request using the supported list contract
- preserve the empty filtered state
- expose `Clear filters` when appropriate

Do not add UI placeholders for unsupported future filters.

Specifically do not add:

- search
- tags
- owners
- archive
- analytics filters
- sorting controls

### 5. Redesign the desktop table

Restyle the Assistants desktop collection table to improve scanability while retaining semantic table markup.

The redesigned table must include:

- assistant identity tile
- combined assistant name and slug presentation
- status badge
- visibility badge
- updated timestamp
- row-action trigger

Combine Name and Slug into one identity column rather than maintaining separate Name and Slug columns.

The identity presentation should contain:

- a compact visual identity tile derived deterministically from the assistant's existing identity/name
- assistant name as the primary text
- slug as supporting/secondary text

Do not introduce avatars, uploaded images, or new backend identity fields.

If the identity tile repeats information already exposed by the assistant name, mark redundant decorative content appropriately so screen-reader users do not hear duplicate identity text.

### 6. Preserve status and visibility badges

Continue using explicit text badges for:

- Active
- Inactive
- Public
- Private

Do not communicate these states through colour alone.

The redesigned badges may change visually, but they must retain accessible visible labels.

### 7. Add selected-row styling without introducing bulk selection

Provide a clear visual treatment for the assistant row currently being interacted with.

Selection styling should correspond to transient row interaction, such as:

- its row-action menu being open
- an action originating from that row being confirmed

Do not interpret this requirement as collection selection.

Do not add:

- row checkboxes
- multi-select
- persistent bulk-selection state
- bulk action controls

Selected styling must not be the sole indication of which assistant an open action menu belongs to.

### 8. Move row operations into an accessible action menu

Remove the current always-visible inline Edit / Activate / Deactivate / Delete controls from each desktop row.

Replace them with one row-action trigger per assistant.

The trigger must have an assistant-specific accessible name, for example:

`Actions for Legal review`

The opened action surface must expose:

- Edit
- Activate or Deactivate, based on current status
- Delete

Requirements:

- fully keyboard operable
- trigger exposes expanded/collapsed state where applicable
- no hover-only functionality
- visible keyboard focus
- action labels remain explicit
- opening one row menu must not leave ambiguous active menus behind
- Escape must allow users to dismiss the menu where the chosen implementation requires explicit dismissal
- focus behaviour must remain predictable when opening and closing the menu
- selecting Edit navigates to the existing edit route
- selecting Activate/Deactivate opens the existing status confirmation workflow
- selecting Delete opens the existing delete confirmation workflow

Prefer an existing project primitive if one exists.

Do not add a dependency solely for this small menu unless the existing project stack cannot implement it safely and accessibly.

### 9. Preserve confirmation behaviour

The row-action redesign must not bypass the existing confirmation dialogs.

Activate/deactivate must continue to:

- confirm before mutation
- warn when deactivating an active public assistant
- use the assistant's `concurrencyToken`
- send only the supported mutation fields
- retain the dialog when mutation errors require correction/retry
- handle update conflicts with the existing safe message
- trigger session expiry for unauthenticated responses
- reload the collection after success

Delete must continue to:

- confirm before deletion
- describe deletion as permanent
- retain dependency/protected-assistant handling
- treat an already-deleted/not-found assistant according to the existing contract
- reload the collection after success

Do not move destructive operations into direct one-click menu actions.

### 10. Preserve pagination

Keep backend pagination unchanged.

The page must continue to use:

- response `limit`
- response `offset`
- response `total`

Previous and Next behaviour must remain backend-offset based.

The current valid-page recovery behaviour after deleting the final item on a later page must remain intact.

Do not replace this with:

- client-side pagination
- an unbounded list request
- infinite scrolling
- pagination based only on loaded item count

### 11. Preserve notices and errors

Retain the existing safe user-facing error mapping.

Preserve behaviour for:

- network failures
- server failures
- invalid responses
- forbidden responses
- unauthenticated/session-expired responses
- mutation conflicts
- protected assistants
- assistants with dependent records
- already-deleted assistants

Successful mutation notices must remain accessible and retain stable focus behaviour.

The redesign must not expose raw backend exceptions.

### 12. Preserve a purpose-built narrow/mobile layout

Do not solve the desktop redesign by forcing the table to remain wide on narrow screens.

At narrow widths, assistants must continue to render as individually understandable cards/rows.

The mobile presentation must expose the same essential information:

- identity
- name
- slug
- status
- visibility
- updated value
- assistant actions

Requirements:

- no page-level horizontal overflow at the target mobile viewport
- controls remain comfortably operable
- action menu remains accessible
- badges wrap without breaking layout
- assistant names/slugs do not force horizontal scrolling
- pagination remains usable
- summary cards reflow appropriately

The implementation may continue using responsive semantic table-to-card rendering or introduce an Assistants-local card presentation if that produces clearer markup, but it must not duplicate business state or backend data-loading logic.

### 13. Keep styles scoped and reusable

Use the existing Admin styling system.

Prefer existing:

- spacing
- typography
- border
- card
- button
- badge
- responsive conventions

Add Assistants-specific classes where the redesigned table/card layout requires them.

Avoid changing generic `table`, `tr`, or `td` rules in a way that redesigns unrelated Admin pages accidentally.

Do not introduce another CSS framework or parallel design system.

### 14. Expand Storybook collection coverage

Update `Assistants.stories.tsx` so the redesigned collection has explicit stories for:

1. Populated
2. Filtered
3. Empty
4. Loading
5. Error
6. Narrow/mobile

Fixtures must be deterministic.

#### Populated

Show a useful mixture of assistants, including different:

- statuses
- visibilities
- update times

The story should make all summary-card variants and badge variants visible.

#### Filtered

Demonstrate the real status/visibility filter behaviour rather than rendering fake static filter labels.

Verify the selected filter affects the mocked list response/request.

#### Empty

Show the unfiltered no-assistants state.

Where useful, also ensure existing tests continue to cover the distinct filtered-empty state.

#### Loading

Keep the request predictably unresolved so the loading UI is visible.

#### Error

Return a deterministic Admin API error and show the safe collection error state.

#### Narrow

Render the populated collection at a representative mobile width and demonstrate the card presentation without horizontal overflow.

Use existing Storybook facilities where available; do not add an addon solely to produce the narrow story if an existing mechanism or constrained wrapper is sufficient.

### 15. Add automated visual regression coverage

This is a material UI redesign.

Add Playwright visual regression coverage for the Assistants collection route using deterministic mocked backend responses.

Prefer a focused file such as:

`apps/admin/e2e/assistants.spec.ts`

Cover the visually material collection states, including:

- populated desktop
- filtered
- empty
- loading
- error
- narrow/mobile

At minimum, functional assertions must accompany screenshots so screenshots are not the sole verification mechanism.

Before taking screenshots:

- mock authentication deterministically
- mock Assistants responses deterministically
- use fixed assistant timestamps
- avoid current-time-dependent output
- use fixed viewport dimensions
- ensure loading state does not race with request completion
- ensure animations/transitions cannot create screenshot instability

For the narrow case, assert programmatically that:

`document.documentElement.scrollWidth <= document.documentElement.clientWidth`

before accepting the screenshot.

Do not use manual Codex visual inspection as the primary evidence that the redesign is correct.

---

## Acceptance criteria

- [ ] Assistants collection has a redesigned page introduction consistent with the Admin UI.
- [ ] Introduction exposes a manual `Refresh` button.
- [ ] Introduction exposes a primary `New Assistant` CTA linking to `/admin/assistants/new`.
- [ ] Manual Refresh reissues `listAssistants` for the current offset and filters.
- [ ] Refresh does not reset active filters.
- [ ] Refresh does not reset the current backend page.
- [ ] Duplicate manual refresh requests are prevented while refresh is pending.
- [ ] Summary shows the exact backend-returned `total`.
- [ ] Backend total is not derived from `page.items.length`.
- [ ] Active count is calculated only from assistants loaded on the current page.
- [ ] Public count is calculated only from assistants loaded on the current page.
- [ ] Private count is calculated only from assistants loaded on the current page.
- [ ] Most recently updated assistant is calculated only from the loaded items.
- [ ] Empty loaded collections render deterministic zero/empty summary values.
- [ ] Only Status and Visibility collection filters are present.
- [ ] Filter changes continue to reset backend offset to zero.
- [ ] Filter values continue to be passed to `listAssistants`.
- [ ] Filtered-empty and unfiltered-empty states remain distinct.
- [ ] Desktop table combines assistant name and slug into one identity presentation.
- [ ] Each assistant has a deterministic identity tile without requiring a new backend field.
- [ ] Status remains visible as an explicit text badge.
- [ ] Visibility remains visible as an explicit text badge.
- [ ] Updated information remains visible.
- [ ] Interacted-with row has deliberate selected/active styling.
- [ ] No persistent or bulk-selection model is introduced.
- [ ] Inline Edit / Activate / Deactivate / Delete controls are replaced by one row-action trigger.
- [ ] Every row-action trigger has an assistant-specific accessible name.
- [ ] Row-action surface is keyboard operable.
- [ ] Edit continues to navigate to the existing edit route.
- [ ] Activate/deactivate continues to require confirmation.
- [ ] Delete continues to require confirmation.
- [ ] Status mutation still sends the assistant concurrency token.
- [ ] Existing public-assistant deactivation warning is preserved.
- [ ] Existing mutation conflict handling is preserved.
- [ ] Existing protected/dependency deletion handling is preserved.
- [ ] Existing session-expiry handling is preserved.
- [ ] Successful mutations still reload the collection.
- [ ] Successful mutation notices retain accessible focus behaviour.
- [ ] Deleting the final item from a later backend page still restores a valid preceding page.
- [ ] Previous/Next pagination remains based on backend `offset`, `limit`, and `total`.
- [ ] No unbounded client-side Assistants load is introduced.
- [ ] Mobile/narrow rendering remains card-oriented rather than a forced wide table.
- [ ] Narrow layout contains no page-level horizontal overflow.
- [ ] All assistant actions remain usable from the narrow layout.
- [ ] New collection styling does not unintentionally alter unrelated Admin tables.
- [ ] Storybook includes populated, filtered, empty, loading, error, and narrow states.
- [ ] Existing create/edit Storybook coverage remains valid.
- [ ] Populated, filtered, empty, loading, error, and narrow collection states have deterministic automated browser coverage where their visual presentation is part of this redesign.
- [ ] Playwright coverage combines functional assertions with screenshot assertions.
- [ ] No search functionality is introduced.
- [ ] No tags functionality is introduced.
- [ ] No owner functionality is introduced.
- [ ] No analytics functionality is introduced.
- [ ] No bulk actions or bulk selection are introduced.
- [ ] No duplicate action is introduced.
- [ ] No archive functionality is introduced.
- [ ] No backend/API contract expansion is required for the redesign.
- [ ] No manual Codex visual inspection is used as the primary proof of correct rendering.

## Tests to add or update

### `apps/admin/src/App.test.tsx`

Update existing Assistants collection tests for the row-action menu interaction.

Existing behavioural coverage must continue proving:

- backend-offset pagination
- supported backend filters
- filtered-empty state
- clear filters
- page correction after deleting the final item on a later page
- protected assistant deletion
- already-deleted assistant handling
- session expiry during mutations
- public deactivation warning
- update concurrency token
- failed status mutation retaining current UI state
- dependency-conflict dialog behaviour
- real HTTP update/delete contract

Add focused tests for:

#### Summary cards

- `total` displays backend `page.total`
- total is not inferred from loaded item count
- Active is derived from loaded items
- Public is derived from loaded items
- Private is derived from loaded items
- most-recent item is selected using `updatedAt`
- empty collection renders zero/empty metrics

Use a fixture where `total > items.length` so backend total and loaded-page counts cannot accidentally be conflated.

#### Refresh

- Refresh calls `listAssistants` again
- current offset is preserved
- status filter is preserved
- visibility filter is preserved
- duplicate Refresh interaction is prevented while pending

#### Row actions

Update tests so they:

1. open the assistant-specific action trigger
2. choose the requested operation
3. verify the existing confirmation/mutation behaviour

Add accessibility-oriented assertions for:

- assistant-specific action trigger name
- expanded/collapsed state where applicable
- action visibility after opening
- menu dismissal/focus behaviour as supported by the chosen implementation

#### Narrow rendering

Keep interaction behaviour independent from viewport-specific implementation details in Vitest; use Playwright for actual layout and overflow verification.

### `apps/admin/src/features/assistants/Assistants.stories.tsx`

Add/update:

- `PopulatedList`
- `FilteredList`
- `EmptyList`
- `LoadingList`
- `ErrorList`
- `NarrowList`

Retain relevant create/edit stories unless this PR makes a small mechanical update necessary.

Update existing interaction stories such as:

- `DeleteConfirmation`
- `PendingStatusAction`

so they use the new row-action menu before invoking the relevant operation.

### `apps/admin/e2e/assistants.spec.ts`

Add deterministic route-level Playwright coverage.

Mock:

- `/admin/auth/me`
- Assistants list endpoint responses

Add functional and visual cases for:

- populated desktop
- filtered result
- empty collection
- loading collection
- collection load error
- narrow/mobile populated collection

Functional assertions should verify important content/interactions before each screenshot.

For narrow coverage:

- use a fixed mobile viewport, e.g. `390 × 844`
- assert no document-level horizontal overflow
- verify assistant identity, badges, updated value, and row actions remain accessible

Store snapshots using the repository's existing platform/naming conventions.

Do not create broad screenshots of unrelated Admin routes in this spec.

## Verification commands

Run focused checks first:

```bash
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx
```

Run the focused browser suite:

```bash
npm run test:e2e --workspace @ai-discovery-assistant/admin -- e2e/assistants.spec.ts
```

When intentionally establishing the new visual baselines:

```bash
npm run test:visual:update --workspace @ai-discovery-assistant/admin -- e2e/assistants.spec.ts
```

Then verify those baselines without update mode:

```bash
npm run test:visual --workspace @ai-discovery-assistant/admin -- e2e/assistants.spec.ts
```

Run the complete Admin verification required by `apps/admin/AGENTS.md`:

```bash
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run test:e2e --workspace @ai-discovery-assistant/admin
npm run test:visual --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
```

Do not report any command as passing unless it was actually executed successfully.
