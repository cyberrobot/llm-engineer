# PR 14B — Add Admin Playwright Visual Regression Infrastructure

## Repository state

Expected branch: feature/14b-admin-playwright-visual-regression

Base branch: main

Worktree: Frontend

Dependencies:

- PR 12H — Path-scoped Admin UI CI must be present so browser and visual tests can be added to the existing required Admin validation workflow rather than creating a competing CI gate.
- PR 13A — Admin Application Foundation must be present.
- PR 14A — Admin Shell Tailwind Redesign should be merged before establishing the initial visual baselines so the repository does not immediately commit obsolete shell screenshots.
- Existing Admin unit tests, Storybook build, CI path filtering, and required-gate behaviour must remain intact.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `package.json`
- `package-lock.json`
- `apps/admin/package.json`
- `apps/admin/README.md`
- `apps/admin/vite.config.ts`
- `apps/admin/vitest.config.ts`
- `apps/admin/src/App.tsx`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/main.tsx`
- `apps/admin/src/test/setup.ts`
- `apps/admin/scripts/verify-ci-workflow.mjs`
- `apps/admin/scripts/run-required-ci-gate.mjs`
- `.github/workflows/test-admin.yml`
- `.github/workflows/test-admin-required.yml`
- `apps/rag-ui/package.json`
- `apps/rag-ui/vitest.config.ts`
- Playwright test documentation for visual comparisons, web servers, projects, retries, reporters, and snapshot updates

### Primary change area

- `apps/admin/package.json`
- `apps/admin/playwright.config.ts`
- `apps/admin/e2e/`
- `.github/workflows/test-admin.yml`
- `apps/admin/scripts/verify-ci-workflow.mjs`
- root `package-lock.json`

### Canonical implementation examples

- Existing Admin CI workflow for Node setup, dependency installation, test execution, linting, type checking, production build, and Storybook build.
- Existing `apps/admin/scripts/verify-ci-workflow.mjs` as the canonical executable contract for required Admin CI steps.
- Existing Admin route tree and UI tests for authoritative paths and user-visible behaviour.
- Existing `apps/rag-ui` browser dependency installation patterns where they are compatible with the Admin implementation.
- Playwright's maintained `@playwright/test` APIs:
  - `playwright.config.ts`
  - `webServer`
  - Chromium projects
  - `expect(page).toHaveScreenshot()`
  - snapshot update commands
  - HTML or CI-suitable reporters
  - traces/screenshots on failure

### Relevant symbols

- `defineConfig`
- `devices`
- `webServer`
- `expect`
- `toHaveScreenshot`
- `test`
- `baseURL`
- `ADMIN_RELEVANT_PATHS`
- `evaluateRequiredGate`
- `verify:ci`
- `test-admin.yml`
- `Admin validation`

Codex must verify the exact Admin authentication and API requirements before selecting initial browser journeys. Do not bypass production authentication semantics merely to make a screenshot test easy.

### Expected change surface

- Introduce `@playwright/test` for `apps/admin`.
- Add a dedicated Playwright configuration for Admin browser and visual regression tests.
- Add the minimum deterministic browser-test infrastructure required to load the Admin application in Chromium.
- Establish initial page-level functional and visual regression tests for stable Admin states.
- Add explicit package scripts for running browser tests, visual tests, and intentional snapshot updates.
- Install Chromium in Admin CI.
- Run the automated browser/visual suite as part of the existing Admin validation job.
- Update the Admin CI verifier so browser testing is part of the executable CI contract.
- Commit deterministic Linux-compatible screenshot baselines suitable for GitHub Actions.

### Excluded areas

- Redesigning any Admin page
- Changing Admin business behaviour
- Changing backend API contracts
- Replacing Vitest or Testing Library
- Replacing Storybook
- Converting existing component/unit tests wholesale to Playwright
- Creating broad end-to-end coverage for every Admin feature
- Adding Cypress, Selenium, Puppeteer, Chromatic, Percy, Applitools, or another competing browser/visual-testing platform
- Testing multiple browser engines unless a verified requirement justifies it
- Testing every responsive breakpoint
- Using screenshot assertions as a substitute for semantic functional assertions
- Automatically accepting changed screenshots in CI
- Storing generated HTML reports, traces, videos, or transient test output in Git
- Backend, database, migration, public widget, Assistant demo, or RAG UI changes unless an unavoidable shared configuration dependency is verified
- Weakening or removing the existing required Admin CI gate
- Commit, push, or pull-request creation

### Unknowns Codex must verify

- The exact `@playwright/test` version compatible with the repository's Node version and dependency graph.
- Whether the Admin app can run against deterministic mocked HTTP responses for browser tests without modifying production behaviour.
- Whether existing development API configuration requires environment overrides for browser tests.
- Whether authentication can be exercised using existing frontend-visible mechanisms or requires deterministic request mocking.
- Which implemented Admin route provides the smallest stable initial visual baseline after PR 14A.
- Whether fonts or platform rendering require repository-local stabilization to keep Linux CI screenshots deterministic.
- Whether transitions or animations exist that must be disabled during screenshot assertions.
- Whether the Vite development server or production preview server is the most reliable Playwright `webServer` target.
- Whether existing CI runners already contain usable Playwright browser dependencies or `playwright install --with-deps chromium` is required.
- The correct snapshot suffix/platform strategy so baselines produced and verified in CI are explicit and reproducible.
- Whether Playwright's HTML report should be retained as a GitHub Actions artifact on failure. If implemented, it must not alter the required check semantics.

---

## Objective

Introduce first-class automated browser and visual regression testing for `apps/admin` so future UI pull requests can verify rendered pages automatically instead of requiring Codex to perform manual visual inspection.

The completed infrastructure must use Playwright with Chromium, execute deterministically locally and in GitHub Actions, combine semantic browser assertions with screenshot comparisons, and form part of the existing required Admin CI validation.

This PR establishes infrastructure and a small representative baseline suite. It must not attempt to convert the Admin application's complete test suite into end-to-end tests.

After this PR, future material Admin UI changes must be able to add or update Playwright tests and visual baselines without introducing additional testing infrastructure.

## Current architecture

`apps/admin` is a React/Vite workspace.

Its current automated test stack consists primarily of:

- Vitest;
- jsdom;
- Testing Library;
- Storybook; and
- the existing Admin CI validation workflow.

`apps/admin/vitest.config.ts` runs tests in jsdom and does not provide a full page-level browser or end-to-end environment.

The Admin package currently exposes scripts for:

- development;
- unit/component tests;
- linting;
- type checking;
- production build;
- CI-workflow verification;
- Storybook; and
- Storybook build.

It does not currently expose a Playwright test command or visual-regression workflow.

`.github/workflows/test-admin.yml` currently runs the required Admin validation steps after `npm ci`, including tests, linting, type checking, production build, and Storybook build.

`apps/admin/scripts/verify-ci-workflow.mjs` acts as an executable specification of that workflow. It explicitly verifies the required Admin validation steps and required-gate behaviour.

Therefore adding Playwright only to `package.json` would be incomplete. Browser installation, execution, CI verification, deterministic baselines, and failure handling must be introduced together.

The intended test layering after this PR is:

```text
Vitest + Testing Library
    ↓
component and application behaviour in jsdom

Storybook
    ↓
isolated deterministic component/page states

Playwright
    ↓
real-browser integration behaviour
    +
visual regression screenshots

Admin UI CI
    ↓
required validation of all applicable layers
```

Snapshots must supplement, not replace, observable behavioural assertions.

## Required implementation

### 1. Add Playwright to the Admin workspace

Add `@playwright/test` as an Admin development dependency using the repository's normal npm workspace workflow.

Update the root `package-lock.json` through npm. Do not edit the lockfile manually.

Do not introduce a second browser automation library.

Use a version compatible with:

- the repository's supported Node version;
- the current npm workspace configuration; and
- GitHub Actions Ubuntu runners.

Do not install Playwright globally.

### 2. Add a dedicated Admin Playwright configuration

Create:

```text
apps/admin/playwright.config.ts
```

The configuration must:

- use `@playwright/test`;
- define the Admin browser-test directory explicitly;
- configure an application `baseURL`;
- start the Admin application automatically with Playwright `webServer`;
- reuse an already-running development server locally where safe;
- fail if the application cannot start;
- run Chromium as the initial and required browser;
- use deterministic viewport and browser settings;
- configure sensible local and CI timeouts;
- avoid arbitrary sleeps;
- enable retries in CI only where justified;
- prevent accidental committed `.only` tests in CI;
- provide useful failure diagnostics;
- retain traces and/or screenshots for failed tests without committing runtime artifacts;
- configure screenshot expectations deliberately rather than relying on undocumented defaults.

Use one Chromium project initially.

Do not add Firefox or WebKit merely for nominal cross-browser coverage.

### 3. Establish deterministic test data and network behaviour

Browser and visual tests must not rely on mutable production or development data.

Use the smallest existing supported mechanism to provide deterministic application state.

Where HTTP mocking is required:

- intercept requests at the browser boundary using Playwright or reuse an established repository mechanism;
- return realistic responses matching actual frontend contracts;
- keep fixtures small and named according to the user-visible scenario;
- do not duplicate large backend implementations in frontend tests;
- do not change production application code solely to expose test hooks.

The initial suite must not require a live external backend, Redis, PostgreSQL, OpenAI provider, or internet access unless repository inspection proves that a lightweight existing integration environment is already canonical.

Authentication must remain representative of the application's real frontend contract.

Do not:

- remove protected-route behaviour;
- disable authentication globally;
- hard-code production credentials;
- store secrets in fixtures; or
- create a production-only bypass for tests.

If network interception is used to establish an authenticated administrator session, it must model the existing public frontend API behaviour rather than bypassing the application state machine.

### 4. Add Admin browser-test scripts

Add clear scripts to `apps/admin/package.json`.

Expected commands should provide the equivalent of:

```json
{
  "test:e2e": "playwright test",
  "test:visual": "playwright test --grep @visual",
  "test:visual:update": "playwright test --grep @visual --update-snapshots",
  "install-playwright": "playwright install --with-deps chromium"
}
```

Exact names may follow stronger existing repository conventions if Codex verifies them.

Requirements:

- normal CI execution must compare against committed baselines;
- snapshot updates must require an explicit developer command;
- CI must never run with `--update-snapshots`;
- updating a screenshot baseline must therefore be a deliberate code-reviewable change.

If tags are used to distinguish visual tests, use normal Playwright-supported metadata or naming conventions rather than a custom test-selection framework.

### 5. Add a small initial browser suite

Create a dedicated test location such as:

```text
apps/admin/e2e/
```

Add a small number of high-value tests proving the infrastructure.

At minimum cover:

#### Authenticated Admin shell

Load an authenticated implemented Admin route using deterministic data.

Assert semantically that:

- the primary navigation is present;
- the expected page heading is present;
- the main landmark is rendered;
- the active navigation state is correct; and
- no generic application error state is present.

Then capture a visual regression screenshot of the stable page state.

#### Responsive Admin shell

Run one deterministic narrow viewport scenario.

Assert that:

- the responsive navigation control is available;
- the page remains usable;
- expected key content remains visible or accessible; and
- the page does not exhibit application-level horizontal overflow.

Capture a visual regression screenshot where the state is stable enough to produce meaningful regression protection.

#### At least one controlled non-default state

Where practical, include one stable user-visible state such as:

- open responsive navigation;
- an empty state;
- a deterministic error state;
- or another existing implemented state with material visual value.

Do not manufacture a product state that the application does not support.

The goal is to prove the infrastructure and establish canonical examples for later PRs, not achieve exhaustive E2E coverage.

### 6. Define visual-regression test rules

Every visual test introduced by this PR must also contain meaningful semantic assertions.

Do not write a test whose only assertion is:

```ts
await expect(page).toHaveScreenshot();
```

Visual assertions are appropriate for regressions involving:

- layout;
- spacing;
- typography;
- visual hierarchy;
- responsive presentation;
- navigation state;
- surface treatment;
- icons;
- borders;
- visibly rendered states.

Functional assertions remain authoritative for:

- routing;
- accessibility semantics;
- API outcomes;
- authentication;
- authorization;
- form submission;
- persisted effects;
- error behaviour;
- state transitions.

Screenshot assertions must use stable targets.

Prefer page or meaningful-region screenshots over many tiny element snapshots when the regression concern is page composition.

Mask or otherwise stabilize genuinely unavoidable dynamic content rather than accepting broad pixel-difference tolerances.

Do not set an excessively permissive global threshold merely to make tests pass.

### 7. Make screenshot output deterministic

Tests must control sources of visual nondeterminism where relevant, including:

- viewport dimensions;
- test data;
- browser engine;
- browser version through the package lock and CI installation;
- animations and transitions;
- timestamps;
- random identifiers;
- loading states;
- asynchronous network completion;
- cursor or focus state where visually significant;
- fonts;
- scroll position.

Use observable conditions such as:

```ts
await expect(...).toBeVisible()
```

rather than arbitrary fixed delays.

Do not use `page.waitForTimeout()` to make screenshot tests appear stable unless Codex documents a browser behaviour for which no observable condition exists.

Commit baselines produced for the canonical CI platform.

Do not generate different untracked baselines silently per developer platform.

If cross-platform snapshot naming is necessary, document the strategy.

### 8. Integrate Playwright into Admin CI

Update:

```text
.github/workflows/test-admin.yml
```

The existing Admin path-scoped workflow must remain the owner of Admin UI validation.

Add browser installation using the supported Playwright command, expected to be equivalent to:

```bash
npx playwright install --with-deps chromium
```

or the corresponding Admin workspace script.

Add a required browser-test step after dependencies are installed and at an appropriate point in the existing validation sequence.

The Playwright test must:

- run on Admin-relevant pull requests;
- run on Admin-relevant pushes to `main`;
- fail the Admin validation job when browser or screenshot assertions fail;
- never use `continue-on-error: true`;
- never automatically regenerate snapshots.

Do not create an independent required check unless repository constraints demonstrate that it is necessary.

The existing required gate should continue to resolve through the `Admin validation` job.

### 9. Update the executable Admin CI contract

Update:

```text
apps/admin/scripts/verify-ci-workflow.mjs
```

so repository tests prove that Playwright validation cannot accidentally disappear from `.github/workflows/test-admin.yml`.

The verifier must assert, at minimum, that the Admin workflow contains:

- dependency installation;
- Playwright Chromium/browser installation;
- Admin browser test execution;
- existing unit tests;
- linting;
- type checking;
- production build;
- Storybook build.

The new Playwright steps must:

- execute whenever the Admin validation job executes;
- not use conditional skipping that can turn relevant Admin changes green without browser tests;
- not use `continue-on-error: true`.

Keep the existing path-filter and required-gate assertions intact.

Do not hard-code irrelevant YAML formatting details.

Verify behaviour and required command presence rather than exact line ordering unless ordering is functionally significant.

### 10. Preserve the required path-scoped CI model

Do not change the existing principle:

```text
Admin-relevant PR
    ↓
Admin UI CI runs
    ↓
Admin UI CI / Required reflects the result

Unrelated PR
    ↓
Admin UI CI may be path-skipped
    ↓
Admin UI CI / Required resolves not-applicable successfully
```

Adding Playwright must not cause the Admin validation workflow to appear on unrelated PRs if the existing path-scoped architecture intentionally avoids that.

Do not create a second always-present Playwright required check.

Browser testing is part of Admin validation, not a separate branch-protection architecture.

### 11. Failure diagnostics

Configure Playwright so a failed browser or visual regression test provides enough evidence to diagnose the problem.

At minimum preserve useful failure output such as:

- expected screenshot;
- actual screenshot;
- diff screenshot;
- Playwright trace where appropriate;
- test report output.

Generated runtime evidence must not be committed to Git.

If useful and simple, upload the Playwright report/test-results directory as a GitHub Actions artifact only when tests fail.

Artifact upload must not:

- hide failures;
- change the required check conclusion;
- require external credentials; or
- introduce a third-party visual-testing service.

### 12. Document the developer workflow

Update `apps/admin/README.md` if necessary to document:

- first-time Chromium installation;
- normal browser-test execution;
- visual-only test execution if separately exposed;
- intentional visual-baseline regeneration;
- reviewing snapshot changes before commit.

Documentation must make clear that:

- snapshot changes are reviewable source changes;
- CI compares against baselines;
- CI never accepts new screenshots automatically;
- manually looking at a page is not a replacement for the automated regression suite.

Keep documentation concise and aligned with actual package scripts.

## Acceptance criteria

- [ ] `@playwright/test` is installed as an Admin development dependency using the repository's normal npm workspace workflow.
- [ ] `package-lock.json` is updated through npm rather than edited manually.
- [ ] `apps/admin/playwright.config.ts` exists and uses the maintained Playwright test runner.
- [ ] Chromium is the single required initial browser project.
- [ ] Playwright starts or connects to the Admin application through a deterministic configured `webServer`.
- [ ] Browser tests do not require production services, credentials, or mutable external data.
- [ ] Authentication test setup preserves the real frontend authentication contract rather than introducing a production bypass.
- [ ] `apps/admin` exposes a normal browser-test command.
- [ ] `apps/admin` exposes an explicit visual-baseline update command.
- [ ] CI never runs with `--update-snapshots`.
- [ ] A dedicated Admin browser-test directory exists.
- [ ] The initial suite includes an authenticated page-level Admin scenario.
- [ ] The initial suite includes a responsive/narrow-viewport scenario.
- [ ] At least one useful stable visual state has committed screenshot coverage.
- [ ] Every visual regression test includes meaningful semantic assertions in addition to screenshot comparison.
- [ ] Browser tests wait for observable conditions rather than arbitrary sleeps.
- [ ] Visual tests control relevant viewport, network, data, animation, asynchronous, and other nondeterministic inputs.
- [ ] Screenshot-difference thresholds are strict enough to catch meaningful regressions and are not globally loosened merely to reduce failures.
- [ ] Committed screenshot baselines are compatible with the canonical GitHub Actions execution environment.
- [ ] `.github/workflows/test-admin.yml` installs the required Chromium/browser dependencies.
- [ ] `.github/workflows/test-admin.yml` runs the Admin Playwright suite for Admin-relevant pull requests and `main` pushes.
- [ ] Browser-test failures fail the existing `Admin validation` job.
- [ ] Browser testing does not use `continue-on-error`.
- [ ] No separate redundant always-required Playwright check is introduced.
- [ ] Existing Admin path filtering remains intact.
- [ ] Existing `Admin UI CI / Required` behaviour remains intact for both Admin-relevant and unrelated PRs.
- [ ] `apps/admin/scripts/verify-ci-workflow.mjs` fails if the browser installation or Playwright execution step is removed from Admin CI.
- [ ] Existing verifier coverage for unit tests, linting, type checking, production build, Storybook build, path filtering, and required-gate behaviour remains intact.
- [ ] Failed Playwright tests provide useful actual/expected/diff output and diagnostic evidence.
- [ ] Generated reports, traces, screenshots from failed runs, videos, and other transient test output are not committed to Git.
- [ ] Snapshot changes require explicit developer action and remain normal reviewable repository changes.
- [ ] Existing Admin Vitest and Storybook infrastructure remains in place.
- [ ] Existing Admin application behaviour is unchanged.
- [ ] No Cypress, Selenium, Puppeteer, Chromatic, Percy, Applitools, or competing browser-testing dependency is introduced.
- [ ] No backend, database, migration, public widget, Assistant demo, or RAG UI behaviour changes are made.
- [ ] Admin unit tests, Playwright tests, lint, type checking, production build, Storybook build, and CI workflow verification all pass.

## Tests to add or update

Add Playwright tests under the dedicated Admin browser-test directory, expected to be:

```text
apps/admin/e2e/
```

Add at least:

### Browser infrastructure smoke/regression test

Verify that:

- Playwright starts the Admin application;
- deterministic API/authentication state can be established;
- an authenticated implemented route renders;
- navigation and main-content landmarks are present;
- the correct page heading appears;
- no generic error state is shown.

### Desktop visual regression

Using the canonical desktop viewport:

- arrange deterministic authenticated administrator and API data;
- navigate directly to one stable implemented Admin route;
- wait for meaningful page content;
- assert important semantic state;
- capture a page-level or meaningful-region screenshot.

The committed baseline must be generated using the canonical environment selected for CI.

### Responsive visual regression

Using one fixed narrow viewport:

- load the same or another appropriate stable route;
- assert responsive navigation behaviour;
- verify no application-level horizontal overflow;
- place the responsive UI into one meaningful stable state if appropriate;
- capture a screenshot.

### Controlled non-default state

Where a currently implemented stable state exists, add one deterministic browser scenario covering something such as:

- open mobile navigation;
- empty data;
- controlled API failure;
- or another visually meaningful existing state.

Do not invent application behaviour solely to create a snapshot.

### CI verifier regression coverage

Update `apps/admin/scripts/verify-ci-workflow.mjs` so it fails if:

- the Playwright browser installation step is missing;
- the Admin browser-test command is missing;
- either step is conditional when the Admin validation job runs;
- either step has `continue-on-error: true`.

Retain existing assertions for all existing Admin validation commands and path-scoped required-gate semantics.

## Verification commands

```bash
# Install repository dependencies.
npm ci

# Install the canonical Playwright browser for Admin tests.
npm run install-playwright --workspace @ai-discovery-assistant/admin

# Verify the Admin CI workflow contract.
npm run verify:ci --workspace @ai-discovery-assistant/admin

# Run existing Admin unit/component tests.
npm test --workspace @ai-discovery-assistant/admin

# Run Admin browser and visual regression tests.
npm run test:e2e --workspace @ai-discovery-assistant/admin

# Verify visual tests through normal comparison mode.
# Do not use the snapshot-update command as final verification.
npm run test:visual --workspace @ai-discovery-assistant/admin

# Run static validation.
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin

# Verify production and Storybook builds.
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

# Snapshot regeneration is a deliberate development operation only.
# Run this only when an intentional visual change requires new reviewed baselines.
npm run test:visual:update --workspace @ai-discovery-assistant/admin
```
