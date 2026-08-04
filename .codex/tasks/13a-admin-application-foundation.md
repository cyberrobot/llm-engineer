# PR 13A — Admin Application Foundation

## Repository state

Expected branch: feature/13a-admin-application-foundation

Base branch: main

Worktree: Frontend

Dependencies:

- PR 11E — Administrator Authentication API must be merged. This PR supplies the authoritative login, logout, current-user, cookie-session, throttling, and lockout contracts used here.
- PR 11A — Assistant Domain and Knowledge Scoping should be present so later admin assistant-management work has a stable backend domain.
- This task must not depend on later assistant-management, knowledge-source-management, ingestion-management, evaluation, or operations frontend PRs.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `package.json`
- `package-lock.json`
- `apps/rag-ui/package.json`
- `apps/rag-ui/src/main.tsx`
- `apps/rag-ui/src/App.tsx`
- `apps/rag-ui/src/services/`
- `apps/rag-ui/vite.config.ts`
- `apps/rag-ui/vitest.config.ts`
- `apps/rag-ui/.storybook/`
- `apps/assistant/AGENTS.md`
- `apps/assistant/src/demo/assistantWidgetDemoConfig.ts`
- `apps/assistant/src/demo/assistantWidgetDemoConfig.test.ts`
- `apps/backend/AGENTS.md`
- `apps/backend/admin_auth/`
- Focused backend tests covering administrator login, logout, current-user, cookie sessions, throttling, and lockout
- `apps/backend/README.md`
- `apps/backend/.env.example`

### Primary change area

- New `apps/admin/` npm workspace application
- Root `package.json` scripts only where required for admin development and verification
- Root `package-lock.json` through normal npm installation
- Admin application source, tests, Storybook configuration, environment example, and README

### Canonical implementation examples

- `apps/rag-ui` for the repository’s established internal React, Vite, TypeScript, ESLint, Vitest, Storybook, and service-boundary conventions
- `apps/assistant` for strict browser configuration validation, safe errors, accessible interaction tests, and deterministic frontend behaviour
- `apps/backend/admin_auth` for the exact authentication HTTP contract
- Existing root workspace scripts and package naming conventions

### Relevant symbols

Codex must verify exact names before implementation. Expected concepts include:

- Administrator login endpoint
- Administrator logout endpoint
- Current authenticated administrator endpoint
- Administrator identity response
- HTTP-only authentication cookie
- `credentials: 'include'`
- Admin API base URL configuration
- Application router
- Protected route
- Authentication/session provider
- Login page
- Admin shell
- Primary navigation
- Session restoration
- Session expiry
- Safe API error mapping

Do not invent endpoint paths, request fields, response fields, cookie names, role values, error codes, or throttling semantics. Read them from the merged backend implementation and its tests.

### Expected change surface

- Add `apps/admin` as a private React/Vite application in the existing `apps/*` workspace.
- Add production-capable application bootstrap and route composition.
- Add a minimal login flow integrated with the real administrator authentication API.
- Restore authenticated state through the backend current-user endpoint.
- Add logout behaviour.
- Add a responsive authenticated shell with placeholder routes for later PRs.
- Add a typed admin API client boundary.
- Add component and integration tests using the repository’s established frontend stack.
- Add representative Storybook stories for reusable foundation states.
- Add environment validation and local setup documentation.

### Excluded areas

- Assistant create, edit, publish, status, or visibility workflows
- Knowledge-source listing, creation, ingestion, re-ingestion, enable/disable, or deletion
- Document or chunk management
- Ingestion progress, evaluations, metrics, audit logs, health dashboards, or operational tooling
- Administrator account creation, invitation, password reset, role management, or profile editing
- Changes to backend authentication behaviour unless a genuine contract defect blocks the frontend; report the mismatch instead of silently changing backend semantics
- Public assistant widget changes
- Functional changes to `apps/rag-ui`
- General-purpose design-system creation
- Arbitrary theming, white-labelling, server-side rendering, or script-tag embedding
- Persisting credentials or session tokens in local storage, session storage, IndexedDB, URLs, or application-managed cookies
- Custom routing, form, query-cache, schema-validation, or HTTP frameworks where a maintained established library is suitable
- Commit, push, or pull-request creation instructions

### Unknowns Codex must verify

- Whether `apps/rag-ui` already uses React Router, TanStack Query, MSW, a form library, or shared test wrappers; reuse established choices where suitable.
- The exact administrator API paths, methods, payloads, response bodies, and status codes.
- Whether the current-user endpoint returns `401`, `403`, or another explicit unauthenticated result.
- Whether logout is idempotent and what response it returns.
- Whether the backend requires CSRF protection or additional headers beyond the HTTP-only cookie.
- The exact credentialed CORS settings required for the admin development origin.
- The repository-supported Node and React versions.
- Whether Storybook test and accessibility tooling is already shared or must be added to `apps/admin`.
- Whether the backend exposes role or permission fields. Render only fields actually present.
- Whether structured backend errors distinguish invalid credentials, throttling, and lockout.
- Whether deployment hosting supports normal browser-history routing without rewrite configuration.

---

## Objective

Create the standalone administrator frontend foundation for Redmoor’s internal management application.

The result must be a private React application under `apps/admin` that starts, builds, lints, type-checks, and tests independently within the monorepo. It must provide validated runtime configuration, routing, authentication and session restoration against the real PR 11E backend API, an accessible login screen, protected-route enforcement, logout, a responsive authenticated shell, and placeholder pages that establish the future administration information architecture.

The foundation must make later admin PRs straightforward. New pages should be able to use a stable route hierarchy, authenticated application context, typed API boundary, shared loading and error treatment, and reusable shell components without replacing the bootstrap.

Security remains server-owned. Client-side route guards may prevent accidental display and guide navigation, but they are not authorization. The backend HTTP-only cookie is the session source of truth. No bearer token, cookie value, password, or session secret may be read, stored, copied, logged, or exposed by the frontend.

## Current architecture

The repository is an npm workspace whose members match `apps/*`. It currently contains a FastAPI backend, an internal React/Vite RAG UI, and the publishable public assistant widget.

The repository map identifies `apps/rag-ui` as the existing internal frontend and directs components to use service modules instead of calling HTTP endpoints directly. The dependency rules define the intended admin direction:

```text
Admin pages
    ↓
Admin API client
    ↓
Backend
```

Admin components must not import backend implementation, persistence, or database code. Frontend types should represent the HTTP contract at the frontend boundary unless the repository already provides a deliberate generated or shared contract package.

PR 11E introduced administrator accounts, password handling, login, logout, current-user behaviour, HTTP-only cookie sessions, role enforcement, secure cookie configuration, throttling, lockout, and tests. That implementation is authoritative. The new application must integrate through credentialed requests and preserve safe backend failure behaviour.

There is currently no `apps/admin` application. This PR therefore owns the initial structure and conventions, but it must avoid speculative abstractions for future features. Adopt the repository’s existing frontend tools and established libraries rather than creating custom routers, caches, form engines, schema validators, or design systems.

## Required implementation

### 1. Create the admin workspace

Create `apps/admin/package.json` as a private workspace package using the repository’s naming convention, expected to be `@ai-discovery-assistant/admin` unless inspection shows a different standard.

Add scripts for development, production build, lint, type-check, tests, and Storybook. Add a Storybook test command only if the repository already supports one or it is introduced using the existing frontend testing stack.

Use the same supported versions of React, React DOM, TypeScript, Vite, ESLint, Vitest, Testing Library, Storybook, and related tooling as the internal frontend where practical. Add React Router, TanStack Query, MSW, a form library, or a schema validator only when actually used and no existing dependency already provides the capability.

Add the standard Vite HTML entry, TypeScript configuration, ESLint configuration, Vitest setup, Storybook setup, application entry point, global styles, and test utilities. Align with current repository versions rather than copying obsolete configuration.

Add root scripts such as `dev:admin`, `build:admin`, `lint:admin`, and `test:admin` where they match existing root conventions. Do not change the meaning of existing commands.

### 2. Validate browser configuration

Add `apps/admin/.env.example` with a public backend base URL setting, expected to be `VITE_ADMIN_API_BASE_URL` unless the repository already defines a suitable shared key.

Create a typed configuration reader that:

- Requires an explicit value and has no silent production fallback.
- Trims whitespace and redundant trailing slashes.
- Accepts only absolute HTTP or HTTPS URLs.
- Rejects embedded credentials, fragments, and unsupported protocols.
- Produces a safe configuration-error screen naming the missing or invalid variable.
- Makes no authentication request when configuration is invalid.
- Treats the value as public browser configuration, not a secret.

Document the local backend URL, expected admin development origin, and credentialed CORS requirements.

### 3. Add the admin API boundary

Create `src/api/` or `src/services/` according to the established `apps/rag-ui` convention. Pages and components must not call `fetch` directly.

The API boundary must:

- Use the validated API base URL.
- Use `credentials: 'include'` for cookie-session requests.
- Send the exact login payload expected by the backend.
- Call the exact logout and current-user endpoints.
- Map successful responses into small frontend-owned types.
- Validate successful response shapes before treating the user as authenticated.
- Map expected HTTP failures into typed safe application errors.
- Preserve request cancellation through `AbortSignal`.
- Never expose or log response bodies, cookies, passwords, stack traces, or backend internals.
- Avoid automatic retries for login, logout, validation failures, unauthenticated responses, throttling, or lockout.
- Permit manual retry of a current-user request after a network or server failure.

Use the repository’s established query/cache library if present. If one is added, configure authentication queries so credentials and authorization failures are not retried in the background.

### 4. Implement routing and authentication state

Create top-level application composition containing:

- Router
- Query or API provider where applicable
- Authentication/session provider
- Route-level error handling or an application error boundary
- Global styles

On first load of a protected route, call the current-user endpoint before rendering protected content.

Required behaviour:

- While session restoration is unresolved, render an accessible full-page loading state. Do not briefly display protected content and do not redirect prematurely.
- When the backend confirms an authenticated administrator, render the requested protected route.
- When the backend confirms no valid session, redirect to login while retaining a safe internal return location.
- After successful login, update or invalidate authentication state and navigate to the validated return location or the default dashboard.
- After logout, clear authenticated frontend state and return to login.
- Refreshing a protected route must restore the session through the HTTP-only cookie.
- External, protocol-relative, malformed, or looping return locations must be rejected to prevent open redirects.
- A network or server failure during session restoration must show a distinct retryable error rather than incorrectly treating the user as logged out.
- If an established authenticated session expires, the application must converge to the logged-out state and stop rendering stale protected content when the backend reports unauthenticated access.

Provide at least these routes:

- `/login`
- Authenticated root route, preferably `/admin` or `/`
- Dashboard placeholder
- Assistants placeholder
- Knowledge Sources placeholder
- Not-found route

Inspect deployment conventions before choosing browser-history or hash routing. Prefer normal browser routing unless hosting constraints require otherwise.

### 5. Implement the login page

Build a focused, professional login screen containing:

- Product or application identity
- Identifier field matching the backend contract
- Password field
- Associated labels
- Required-field validation
- Password-manager-friendly autocomplete values
- Keyboard submission
- Pending state
- Duplicate-submission prevention
- Safe invalid-credentials feedback
- Safe throttling or lockout feedback only where the backend contract distinguishes it
- General network or server failure feedback
- Preservation of the identifier after failure
- No password persistence or logging
- Appropriate focus movement to invalid fields or an error summary

Use an existing form and validation library if already established. Otherwise keep the implementation small and direct. Do not create a reusable form framework.

An already authenticated administrator visiting `/login` should be redirected after session restoration completes.

### 6. Build the authenticated shell

Create a responsive, accessible application shell that establishes the later admin information architecture without implementing future management features.

Include:

- Skip link
- Application header
- Primary navigation
- Current administrator identity using only backend contract fields
- Logout action
- Main content landmark
- Page heading area
- Desktop and small-screen navigation treatment
- Visible active-route indication
- Sensible focus behaviour after navigation
- Placeholder pages for Dashboard, Assistants, and Knowledge Sources

Avoid a large design system. Extract only components justified by this PR, such as `AdminShell`, `PrimaryNavigation`, `PageHeader`, `FullPageStatus`, or `ConfigurationError`.

Placeholder pages must clearly state that functionality is not implemented yet. Do not show fake data or disabled controls that imply working features.

### 7. Styling, accessibility, and stories

Use one coherent Redmoor admin visual treatment. Keep styles application-local and independent of the public widget stylesheet.

The application must remain usable at narrow mobile widths and normal desktop widths. Navigation, login, errors, and logout must be keyboard reachable. Use semantic HTML before ARIA. Provide visible focus, associated validation messages, correct heading order, adequate contrast, and no core-layout horizontal overflow.

Add deterministic Storybook stories for reusable foundation states, including:

- Login default
- Login submitting
- Login invalid credentials or general error
- Admin shell desktop
- Admin shell constrained or mobile width
- Full-page loading
- Session restoration failure
- Configuration error

Use fictional administrator data and fixed values.

### 8. Documentation

Add `apps/admin/README.md` covering:

- Purpose and current scope
- Local installation and development
- Required environment setting
- Backend startup dependency
- Credentialed CORS requirements
- High-level session restoration behaviour
- Lint, type-check, test, build, and Storybook commands
- Placeholder routes and explicit exclusions
- Troubleshooting for missing configuration, backend unavailability, CORS rejection, invalid credentials, throttling or lockout where applicable, and expired sessions

Do not document real credentials. Reference the backend-supported administrator bootstrap process rather than duplicating or bypassing it.

## Acceptance criteria

- [ ] `apps/admin` is a private npm workspace application installed through the root lockfile.
- [ ] The application starts with a repository-standard root command.
- [ ] Admin lint, type-check, tests, and production build pass independently.
- [ ] Missing or invalid API configuration displays safe actionable guidance and sends no auth request.
- [ ] Login uses the exact PR 11E contract and `credentials: 'include'`.
- [ ] Passwords, cookies, and session data are never persisted or logged.
- [ ] Successful login establishes authenticated state and navigates to a safe intended route.
- [ ] Invalid credentials remain on the login page and show an accessible safe error.
- [ ] Throttling or lockout is shown only when contractually distinguishable.
- [ ] Duplicate login submission is prevented while pending.
- [ ] Protected routes do not render before current-user confirmation.
- [ ] Refreshing a protected route restores the cookie-backed session.
- [ ] A confirmed unauthenticated result redirects to login.
- [ ] Session-check network or server failure shows a retryable error and does not misclassify the user as unauthenticated.
- [ ] Malformed or external return locations cannot create an open redirect.
- [ ] Logout calls the backend, clears frontend auth state, and returns to login.
- [ ] Repeated logout or an expired session converges safely to logged-out state.
- [ ] The authenticated shell exposes accessible navigation, identity, logout, and main content.
- [ ] Dashboard, Assistants, and Knowledge Sources exist as honest placeholders without fake functionality.
- [ ] Unknown routes show a not-found page with a recovery action.
- [ ] Core login and shell workflows are keyboard usable and work at mobile width.
- [ ] Reusable states have deterministic Storybook stories.
- [ ] No page or component performs direct HTTP requests outside the admin API boundary.
- [ ] No backend implementation module is imported by the frontend.
- [ ] Existing backend, RAG UI, and assistant-widget behaviour remains unchanged.
- [ ] `apps/admin/README.md` accurately documents setup, authentication, checks, and limitations.

## Tests to add or update

Add tests beside the affected code using Vitest, React Testing Library, and `userEvent`. Use MSW at the HTTP boundary when already established or introduce it as the maintained network mock rather than mocking authentication hooks.

Cover:

- Configuration normalization, missing values, unsupported protocols, embedded credentials, fragments, and trailing slashes.
- API paths, methods, headers, payloads, `credentials: 'include'`, cancellation, malformed success responses, safe error mapping, and raw-response non-disclosure.
- Login required fields, keyboard submission, successful login, invalid credentials, pending state, duplicate prevention, network failure, and throttling or lockout where supported.
- Protected-route loading with no protected-content flash.
- Authenticated session restoration.
- Confirmed unauthenticated redirect with a safe return path.
- Session-check server or network failure and manual retry.
- Rejection of external, malformed, protocol-relative, and looping return locations.
- Redirect away from login when already authenticated.
- Logout success, already-expired session handling, and contractually correct logout failure behaviour.
- Active navigation, shell landmarks, identity display, mobile navigation, and not-found recovery.
- Session expiration during authenticated use if the chosen API/query architecture provides a central response mechanism.

Use semantic selectors and observable behaviour. Do not test private hook state, CSS classes, router internals, or query-library internals.

Add Storybook play tests only where they provide distinct value. Do not duplicate every component test.

Add Playwright coverage only if the repository already has suitable infrastructure. Otherwise do not introduce a broad end-to-end harness in this foundation PR.

## Verification commands

Codex must verify the exact workspace name and available scripts before running commands. Expected commands are:

```bash
npm ci

npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin

# Run the repository-supported Storybook interaction/accessibility command
# for the admin workspace if configured.

# Confirm lockfile and workspace changes did not break existing frontends.
npm run build --workspace @ai-discovery-assistant/rag-ui
npm run build --workspace @redmoor/assistant-widget

# Run the focused backend admin-auth tests whose paths Codex verified.
npm run test:api -- <verified admin-auth test paths>

git diff --check
```
