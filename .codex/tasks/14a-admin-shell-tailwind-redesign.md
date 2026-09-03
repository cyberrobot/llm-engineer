# PR 14A — Redesign the Admin Shell with Tailwind CSS

## Repository state

Expected branch: feature/14a-admin-shell-tailwind-redesign

Base branch: main

Worktree: Frontend

Dependencies:

- PR 13A — Admin Application Foundation must be merged. This PR reuses its authenticated shell, routing, session restoration, logout, focus management, and Storybook foundation.
- PR 13E and PR 13G — Admin Dashboard and Operations UI must be present so the redesigned navigation can link to every implemented Operations route and be regression-tested against real page content.
- The current Assistant management, Behaviour, Preview, Knowledge Sources, and Operations routes must remain available without contract changes.
- This PR is the first UI-redesign PR. It must not depend on the later Assistants collection or Assistant detail-drawer redesigns.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `package.json`
- `package-lock.json`
- `apps/admin/README.md`
- `apps/admin/package.json`
- `apps/admin/vite.config.ts`
- `apps/admin/vitest.config.ts`
- `apps/admin/.storybook/main.ts`
- `apps/admin/.storybook/preview.ts`
- `apps/admin/src/main.tsx`
- `apps/admin/src/App.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/components/AdminShell.tsx`
- `apps/admin/src/components/Foundation.stories.tsx`
- `apps/admin/src/styles.css`
- Official Tailwind CSS Vite installation documentation: `https://tailwindcss.com/docs/installation/using-vite`

### Primary change area

- `apps/admin/src/components/AdminShell.tsx`
- Admin-shell styling in `apps/admin/src/styles.css`
- `apps/admin/src/components/Foundation.stories.tsx`
- Shell workflow coverage in `apps/admin/src/App.test.tsx`
- Tailwind integration in `apps/admin/vite.config.ts`
- Tailwind development dependencies in `apps/admin/package.json`
- Root `package-lock.json`, updated only through the normal npm installation workflow

### Canonical implementation examples

- The existing `AdminShell` for authentication, logout, route-aware headings, navigation focus, mobile-menu state, skip-link behaviour, and protected content composition.
- The existing `App` route tree for the complete set of supported destinations. Navigation labels and links must be derived from implemented routes rather than from unsupported mockup items.
- Existing Admin tests for authenticated landmarks, active navigation, deep links, logout, and session expiry.
- Existing Admin Storybook stories for deterministic desktop and constrained-width shell states.
- Tailwind CSS's maintained Vite integration using `tailwindcss`, `@tailwindcss/vite`, the Vite plugin, and `@import "tailwindcss";`.

### Relevant symbols

- `AdminShell`
- `links`
- `titleFor`
- `NavLink`
- `Outlet`
- `useLocation`
- `useNavigate`
- `useAuth`
- `auth.logout`
- `heading`
- `open`
- `primary-nav`
- `skip-link`
- `app-shell`
- `brand`
- `identity`
- `menu-button`
- `ShellDesktopAuthenticated`
- `ShellMobileAuthenticated`

Codex must verify exact route paths and page-title behaviour before changing the navigation model. Do not invent destinations, roles, administrator fields, or product capabilities.

### Expected change surface

- Add Tailwind CSS to the Admin workspace through its official Vite integration.
- Replace the current top-header and light navigation rail with a full-height dark teal desktop sidebar and a compact responsive mobile header/navigation drawer.
- Add the redesigned product identity, route icons, hierarchical Operations navigation, administrator identity, and sign-out action.
- Preserve the existing main-content heading, route outlet, skip link, focus restoration, authentication behaviour, and logout semantics.
- Retain the existing application stylesheet for pages not owned by this PR. Migrate only shell-owned presentation to Tailwind utilities.
- Update deterministic shell stories and behaviour-focused tests.

### Excluded areas

- Redesigning the Assistants summary cards, filters, table, pagination, row actions, or empty states
- Adding the Assistant detail drawer
- Redesigning Assistant create/edit, Behaviour, Preview, Knowledge Sources, Dashboard, or Operations page content
- Changing Admin API requests, response models, authentication, authorization, session restoration, logout, or error mapping
- Adding unsupported Settings, owner, tags, analytics, bulk actions, archive, duplication, or publication-list features
- Backend, database, migration, public widget, Assistant demo, or RAG UI changes
- Replacing React Router or introducing a component framework
- Adding a general-purpose design-system package
- Adding `clsx`, a CSS-in-JS library, an icon package, or another styling dependency when small local markup is sufficient
- Migrating all of `apps/admin/src/styles.css` to Tailwind in this PR
- Changing the established Admin routes or browser-history hosting requirements
- Commit, push, or pull-request creation

### Unknowns Codex must verify

- The current repository-supported Node version and the mutually compatible versions of `tailwindcss` and `@tailwindcss/vite` for the installed Vite version.
- Whether Storybook automatically merges `apps/admin/vite.config.ts` in the installed version or needs a minimal `viteFinal` addition for Tailwind processing.
- Whether Tailwind Preflight changes any existing Admin page presentation or semantics. If it does, add the smallest application-local compatibility styles; do not redesign unrelated pages.
- Whether the current Admin Storybook build resolves Tailwind utilities without additional content/source configuration.
- Whether inline SVG icons can cover the required navigation vocabulary without a new dependency.
- The desired product label from the approved mockup. Unless product direction says otherwise, use `Assistant Platform` in the shell while retaining Redmoor identification in document metadata and existing documentation.
- Whether the administrator email can be long enough to require truncation and an accessible full-value treatment.
- Whether the mobile navigation needs an overlay to prevent interaction with obscured content at the existing supported narrow widths.

---

## Objective

Redesign the authenticated Admin application shell to match the approved Assistant Platform visual direction while preserving all existing routes, authentication behaviour, accessibility guarantees, and page functionality.

The completed shell must use Tailwind CSS utilities for its layout and visual presentation. On desktop it must provide a full-height deep-teal sidebar with clear product identity, route hierarchy, active states, administrator context, and sign-out. On smaller screens it must provide a compact header and an accessible collapsible navigation treatment without horizontal overflow or hidden core actions.

This is a presentation and information-architecture change, not a functional rewrite. Existing pages must continue rendering through the same `Outlet`, use the same Admin API and authentication provider, and retain their current business behaviour. The implementation must create a stable visual foundation for later Assistants-page PRs without prematurely implementing those PRs.

## Current architecture

`apps/admin` is a private React/Vite workspace application. `src/main.tsx` imports the application-wide `styles.css`, creates the browser router, constructs the Admin API client, and provides authenticated state through `AuthProvider`.

`App.tsx` owns the route tree and renders protected routes through `AdminShell`. `AdminShell` currently owns:

- the skip link;
- a horizontal application header;
- product branding;
- the responsive menu toggle;
- administrator identity and logout;
- primary navigation;
- route-aware page titles;
- focus movement to the new page heading; and
- the `Outlet` for page content.

The current visual implementation uses global class selectors in `src/styles.css`. That stylesheet also contains the presentation for every implemented Admin feature, so wholesale replacement would create an unnecessarily large and risky change.

The route tree already contains Dashboard, Operations, Assistants, Assistant Behaviour, Preview, Assistant-scoped Knowledge, and Knowledge Sources. The backend and `adminApi` are not involved in shell rendering beyond the authenticated administrator identity and logout operation.

The required dependency direction remains:

```text
Admin shell and pages
    ↓
Authentication context / Admin API client
    ↓
Backend
```

Tailwind is a build-time styling dependency. It must not introduce runtime state, bypass component boundaries, or change this dependency direction.

## Required implementation

### 1. Add Tailwind CSS through the official Vite integration

Add `tailwindcss` and `@tailwindcss/vite` to the Admin workspace development dependencies using npm from the repository root. Update `package-lock.json` through npm; do not edit the lockfile manually.

Update `apps/admin/vite.config.ts` to register the official Tailwind Vite plugin alongside the existing React plugin and preserve the `@redmoor/assistant-widget` alias.

Import Tailwind from `apps/admin/src/styles.css` using the supported Tailwind CSS syntax. Keep the stylesheet imported once from `src/main.tsx` and once from the Admin Storybook preview as it is today.

Use Tailwind's CSS-first theme configuration to define the approved application colors and any genuinely reused shell tokens. Expected visual tokens include:

- deep teal navigation surface;
- darker teal hover/pressed surface;
- brighter teal active surface;
- warm copper accent;
- warm off-white application canvas;
- white content surfaces;
- muted gray text and borders; and
- a high-contrast focus color.

Do not add a JavaScript Tailwind configuration file unless the installed Tailwind version or a verified repository constraint requires it. Do not use the Play CDN.

Tailwind utility class names must be statically discoverable. Do not construct partial utility names dynamically.

### 2. Keep the migration bounded to the shell

Use Tailwind utilities directly in `AdminShell.tsx` for shell layout, sizing, spacing, typography, colors, borders, responsiveness, hover states, focus-visible states, and transitions.

Retain existing CSS for page content outside the shell. Remove or reduce legacy shell selectors only after their Tailwind replacements are verified. Do not mechanically translate or reformat unrelated feature styles.

If Tailwind Preflight affects existing buttons, tables, dialogs, forms, headings, or links, preserve their existing usable presentation with the smallest scoped compatibility rules. A page-wide redesign must not be smuggled into this PR as Preflight cleanup.

Do not use `@apply` to recreate large semantic component classes. A small base rule is acceptable only when a pseudo-element, browser behaviour, or cross-page invariant cannot be expressed clearly with utilities.

### 3. Implement the desktop shell

At normal desktop widths, render a two-column application shell:

- a full-height sidebar approximately 15–17rem wide;
- a flexible main-content column that can shrink without overflow;
- a sidebar that remains visible while long page content scrolls; and
- a warm off-white main canvas with the existing page heading and route content.

The sidebar must contain:

1. Product identity at the top, using `Assistant Platform` unless verified product guidance requires the existing name.
2. Primary links for Dashboard, Assistants, and Knowledge Sources.
3. An Operations group containing links to the implemented Overview, Health, Jobs, Cache, and Maintenance routes.
4. A separate `Audit & Activity` link targeting the implemented audit route.
5. The authenticated administrator identity and `Platform Administrator` role label in the footer.
6. A visible Sign out action.

Do not add Settings or another destination without a corresponding implemented route.

Use small local inline SVG icons marked decorative where their adjacent text supplies the accessible name. Icons must use `currentColor`, remain sharp at the rendered size, and not require an icon dependency.

The currently selected route must have a clear non-color-only indication such as an accent edge, marker, or weight change. Parent Operations state must remain evident on nested Operations routes. `NavLink` and the current route tree remain authoritative.

The main page heading must remain the first visible heading for the current route and must continue receiving focus after pathname changes.

### 4. Implement responsive navigation

Below the desktop breakpoint:

- replace the persistent sidebar with a compact application header;
- expose a clearly labelled menu button with accurate `aria-expanded` and `aria-controls` values;
- render the same navigation destinations and administrator actions in the mobile panel;
- close the menu after route selection;
- close the menu on Escape;
- prevent an open panel from making obscured content confusing or accidentally interactive where an overlay is used;
- retain access to Sign out; and
- avoid horizontal scrolling at a 320px viewport width.

The mobile implementation may share markup with desktop or use a small extracted navigation component. Do not duplicate route definitions or logout business logic.

When navigation changes from mobile to desktop width, stale open/closed state must not hide desktop navigation or trap focus.

### 5. Preserve authentication and routing behaviour

Do not change `AuthProvider`, protected-route logic, API calls, or authentication state.

Logout must continue to:

- call the existing `auth.logout()` operation;
- converge to the logged-out state even if the backend session is already expired;
- navigate to `/login` with replacement; and
- avoid displaying raw backend failures.

The shell must render only when the existing protected-route contract supplies an authenticated user. Render only administrator fields that already exist in the frontend type.

Keep every existing route and `titleFor` result working. If navigation metadata is refactored, it must remain a presentation-owned, frontend-only structure with deterministic labels and destinations.

### 6. Accessibility requirements

Preserve the skip link and ensure it becomes visible when focused.

Required semantics include:

- one primary navigation landmark with a stable accessible name;
- one main content landmark with the skip-link target;
- correct `aria-current` state from active navigation links;
- an associated menu button and mobile navigation panel;
- decorative icons hidden from assistive technology;
- visible focus indicators on links, buttons, and the route heading;
- sufficient contrast for default, hover, active, disabled, and focus states;
- logical keyboard order; and
- no focus trap or inaccessible hidden navigation.

Do not add ARIA where semantic elements already provide the correct behaviour.

### 7. Update stories and tests

Update the existing shell stories to use fixed fictional administrator data and real implemented route labels.

Storybook must include at least:

- authenticated desktop shell;
- authenticated constrained-width/mobile shell;
- an Operations nested route showing parent and child active states;
- a long administrator email state; and
- mobile navigation open.

Stories must not make live backend requests.

Update behaviour-focused tests before or alongside implementation. Tests must assert navigation, focus, mobile state, logout, and accessibility semantics rather than Tailwind class strings or exact visual markup.

### 8. Documentation and change boundaries

Update `apps/admin/README.md` only if the local development or contributor workflow changes. Tailwind must require no separate global installation or CDN step.

Do not describe the later Assistants-page redesign as implemented. Do not add screenshots that can become stale unless the repository already maintains visual documentation in that form.

## Acceptance criteria

- [ ] `tailwindcss` and `@tailwindcss/vite` are scoped to the Admin workspace and recorded in the root lockfile through npm.
- [ ] The Admin Vite build uses the official Tailwind Vite plugin while preserving the React plugin and Assistant widget alias.
- [ ] Tailwind is loaded through the existing Admin stylesheet and works in both the application and Storybook build.
- [ ] No Play CDN, runtime Tailwind compiler, CSS-in-JS library, component framework, `clsx`, or icon package is introduced.
- [ ] `AdminShell.tsx` uses Tailwind utilities for the redesigned shell presentation.
- [ ] Legacy shell CSS is removed only where its replacement is complete; unrelated Admin feature CSS is not migrated or reformatted.
- [ ] Desktop layout renders a full-height dark teal sidebar and flexible main-content area without core-layout horizontal overflow.
- [ ] The sidebar shows Assistant Platform identity, Dashboard, Assistants, Knowledge Sources, Operations children, Audit & Activity, administrator identity, and Sign out.
- [ ] Every navigation item targets an existing route.
- [ ] No unsupported Settings or placeholder destination is added.
- [ ] Active top-level and nested routes have an accessible, non-color-only visual indication.
- [ ] Existing route titles remain correct.
- [ ] The current page heading continues receiving focus after pathname changes.
- [ ] The skip link remains keyboard reachable, becomes visible on focus, and targets the main content landmark.
- [ ] Mobile navigation exposes correct expanded state, contains the same destinations and account actions, and closes after selection or Escape.
- [ ] The shell remains usable without horizontal overflow at 320px width.
- [ ] A long administrator email does not break the sidebar and its complete value remains available accessibly.
- [ ] Logout retains its current safe success and already-expired-session behaviour.
- [ ] Protected content, session restoration, and Admin API behaviour remain unchanged.
- [ ] Existing Dashboard, Operations, Assistants, Behaviour, Preview, and Knowledge pages remain usable under the redesigned shell.
- [ ] Tailwind Preflight does not leave existing forms, tables, buttons, dialogs, headings, or links unusable.
- [ ] Navigation icons are local, decorative inline SVGs that use `currentColor`.
- [ ] Shell interaction tests assert user-visible behaviour and semantics rather than Tailwind implementation details.
- [ ] Deterministic desktop, mobile, nested Operations, long-email, and open-navigation stories exist.
- [ ] Admin tests, lint, type checking, production build, CI workflow verification, and Storybook build pass.
- [ ] No backend, database, migration, public widget, Assistant demo, or RAG UI files are changed.
- [ ] Documentation accurately reflects any changed local setup and does not claim later UI work is complete.

## Tests to add or update

Update `apps/admin/src/App.test.tsx` and, if a smaller component test gives clearer ownership, add a focused test beside `AdminShell.tsx`.

Cover:

- The authenticated shell exposes the Primary navigation and main content landmarks.
- Dashboard, Assistants, Knowledge Sources, Operations Overview, Health, Jobs, Cache, Maintenance, and Audit & Activity links have the correct destinations.
- Dashboard uses exact matching and does not remain active on unrelated routes.
- Operations parent and the correct child state are indicated on nested Operations routes.
- Assistant subroutes keep Assistants active.
- The route heading changes and receives focus after navigation.
- The skip link points to the main landmark.
- Mobile menu starts collapsed, opens from the menu button, reports `aria-expanded="true"`, and closes after selecting a route.
- Mobile menu closes on Escape and returns focus to the menu button where appropriate.
- The administrator email and role label are rendered without inventing backend fields.
- Sign out calls the existing logout operation once and navigates to login.
- An already-expired logout still converges to login.
- No unsupported Settings navigation item is rendered.

Update `apps/admin/src/components/Foundation.stories.tsx` with deterministic stories for:

- desktop authenticated shell;
- constrained/mobile authenticated shell;
- open mobile navigation;
- nested Operations navigation state; and
- long administrator email.

Do not assert generated Tailwind CSS, utility-class ordering, exact SVG paths, pixel values, or component internals.

## Verification commands

Run from the repository root with the repository-supported Node version.

```bash
# Focused Admin workflow tests
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx

# Complete Admin verification
npm run test:admin
npm run lint:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run build:admin
npm run verify:ci --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

# Broader frontend regression coverage because the root lockfile changes
npm test

# Patch hygiene
git diff --check
```

Manually verify the built or development application at these representative widths:

- 1440px desktop;
- 768px tablet boundary;
- 390px mobile; and
- 320px minimum narrow viewport.

At each width, verify navigation reachability, active state, heading focus, sign out, main-content scrolling, and absence of core-layout horizontal overflow. Also inspect at least Dashboard, Assistants, an Assistant subroute, Operations Overview, an Operations child route, and Knowledge Sources to catch Tailwind Preflight regressions.

Do not claim completion if a relevant command fails. If a command cannot run, report the exact command, reason, observed error, and remaining verification risk.
