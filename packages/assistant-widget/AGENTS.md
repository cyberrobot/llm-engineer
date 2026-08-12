# Frontend Engineering Rules

## Repository Navigation

Read the root `AGENTS.md`, `docs/architecture/repository-map.md`, and
`docs/architecture/dependency-rules.md` before changing the assistant widget. Start at the narrowest
affected public or internal boundary:

- `src/index.ts`, `src/AssistantWidget.tsx`, and `src/AssistantWidget.types.ts` for the supported
  package surface.
- `src/components/assistant-widget/` for rendered conversation behaviour and bounded state.
- `src/publicChatClient.ts` and `src/api/` for the public backend transport contract.
- `src/config/` for validated browser configuration.
- `apps/assistant-demo/src/` only for local consumer behaviour that depends on the package API.
- `test-fixtures/consumer/` and `scripts/` only when package exports or distributable contents change.

Follow component imports and public exports from the affected file; do not scan all widget source or
the demo by default. Treat `package.json` exports, compiled styles, peer dependencies, and consumer
fixtures as package contracts, but inspect them only when the requested change can affect consumers.

## Frontend Testing

Add or update frontend tests whenever user-visible behaviour changes. Exercise the rendered interface through text, accessible roles, labelled controls, keyboard and pointer input, and navigation; do not test hook internals, component state, exact DOM structure, CSS classes, or generated IDs when a behavioural alternative exists. A frontend feature is incomplete unless its meaningful success, loading, empty, failure, disabled, and accessibility states are covered where applicable.

Use the repository's existing frontend stack. When the repository has no established alternative, use:

- Vitest for unit and component integration tests.
- React Testing Library and `userEvent` for rendered interaction tests.
- Storybook for reusable components, distinct feature states, and component interaction tests.
- Mock Service Worker (MSW) for HTTP mocking in tests and Storybook.
- Playwright for a small number of critical full-application journeys.
- Storybook accessibility tooling based on axe-core for automated checks.

Do not add overlapping test libraries without a documented technical reason. Most frontend coverage should come from component integration tests and representative Storybook stories; reserve isolated unit tests for substantial standalone logic such as validation, reducers, state machines, transformations, permission calculations, protocol mapping, and complex hooks that cannot be tested more clearly through a component.

### Component tests and stories

Create stories for reusable components and meaningful feature states, including default, empty, loading or submitting, success, error, disabled, long-content, constrained-width, permission-restricted, unusual valid data, and boundary states when relevant. Do not create stories solely for cosmetic permutations unless they are part of the supported API.

Use Storybook play functions for interactions naturally demonstrated by a story, such as form submission, dialogs, selection, retries, messaging, navigation, and keyboard behaviour. Use React Testing Library for component or feature integration scenarios that are clearer outside Storybook. Do not duplicate the same behaviour in both unless each test provides materially different coverage.

Component tests should normally:

1. Arrange API handlers, props, and application state.
2. Render through the project test wrapper.
3. Interact with `userEvent`.
4. Assert observable user-facing results.

Prefer `getByRole`, `getByLabelText`, `getByText`, and their asynchronous `findBy` forms. Use `queryBy` for absence and `data-testid` only when no practical semantic selector exists. Prefer `userEvent` over `fireEvent`.

### Network and asynchronous behaviour

Mock network behaviour with MSW at the HTTP boundary rather than mocking hooks or API clients, unless HTTP mocking is impractical or the client itself is under test. Cover relevant success, empty, validation, authentication, authorisation, rate-limit, server, network, delayed, and malformed-response outcomes. Reset handlers and shared state between tests, and fail tests on unexpected requests.

Assert asynchronous behaviour through observable state changes: loading indicators, disabled controls, duplicate-submission prevention, success and error output, retry behaviour, cancellation or unmount safety, and protection against stale responses and rapid repeated interactions. Wait for visible state, requests, or navigation; never use arbitrary sleeps or increase timeouts to hide synchronization defects.

Form coverage should include relevant initial values, required fields, valid and invalid submission, field and server validation, loading, duplicate prevention, value preservation or clearing after failure, keyboard submission, associated error messages, and focus movement after validation failure. Test the rendered form, not the form library.

### Accessibility, responsive, and visual coverage

Use semantic HTML and accessible names as the first accessibility boundary. Check important stories and journeys for labels and names, valid ARIA, heading structure, colour contrast, keyboard operation, associated errors, and focus movement and restoration for dialogs, menus, popovers, and other layered UI. Automated axe checks supplement rather than replace manual keyboard and screen-reader review of critical flows.

Add stories or tests when layouts materially change by viewport. Verify readability, reachability, overflow, dialog fit, intentional table scrolling or degradation, unobscured content, usable touch targets, and completion of the main workflow at mobile widths. Do not assert exact pixels unless they are a public contract.

Use Storybook-based visual regression tests for important stable states such as core layouts, conversations, forms, tables, dialogs, responsive layouts, long content, loading, empty, and error states. Keep baselines deterministic with fixed dates and data and no uncontrolled animation, randomness, or timestamps. Review intentional visual changes before updating baselines; visual regression detects change but does not establish correctness.

### End-to-end tests

Use Playwright for a small number of critical journeys such as public assistant conversations, authentication, protected routes, refresh persistence, important record workflows, administration, frontend-to-backend integration, and cookie, routing, or deployment configuration. End-to-end tests prove that major parts work together; do not reproduce every component edge case. Each test must arrange and clean up its own data, run independently, use semantic selectors, wait for observable conditions rather than arbitrary delays, and verify final user-visible and persisted outcomes.

### Frontend test data and organization

Use small, explicit, meaningful fixtures with fixed timestamps and deterministic identifiers. Add builders or factories only when they reduce duplication without hiding scenario setup. Never use production credentials, personal data, or secrets.

Keep tests beside the code they verify unless the repository has a different convention. Avoid large DOM or page snapshots; use snapshots only for small stable serialized outputs or intentional compact structural contracts.

Before declaring frontend work complete, run the repository-equivalent type-check, lint, test, and production-build commands plus configured Storybook interaction, accessibility, visual, and Playwright suites. Use existing package-manager scripts, keep configured coverage thresholds satisfied, and never update visual baselines, disable checks, or reduce thresholds merely to make validation pass.

Test names must state the scenario, action, and expected outcome. Factories should provide valid defaults with focused overrides; avoid large irrelevant fixtures or fixed IDs that can collide.
