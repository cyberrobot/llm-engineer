PR 12F — Scope Assistant Widget CI to Relevant Changes

Repository state

Expected branch:

feature/12f-scope-assistant-widget-ci

Base branch:

main

Worktree:

Frontend

Dependencies:

- Existing @redmoor/assistant-widget package
- PR 12E — Assistant Package Structure and Standard Changesets Release Workflow
- Existing Changesets configuration
- Existing .github/workflows/test.yml
- Existing .github/workflows/publish-assistant-widget.yml

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .github/workflows/test.yml
- .github/workflows/publish-assistant-widget.yml
- .changeset/config.json
- package.json
- package-lock.json
- packages/assistant-widget/package.json
- .codex/tasks/12e-assistant-package-structure-and-changesets-release.md
- .codex/tasks/12e-assistant-package-structure-and-changesets-release-review1.md

Inspect PR #81 as the concrete example demonstrating the current CI problem.

PR #81 modifies Admin UI and task-spec files only and does not modify the Assistant widget package or its release inputs.

Primary change area

- .github/workflows/test.yml
- CI documentation where existing repository documentation describes required checks

Canonical implementation examples

Use native GitHub Actions path/change filtering or an established maintained action already present in the repository where appropriate.

Prefer simple declarative filtering over custom shell scripts.

Conceptually:

Pull request
↓
Determine changed areas
↓
Assistant widget affected?
/ \
 yes no
↓ ↓
run widget CI skip widget CI

Relevant changes should include direct widget changes and repository-level files that can materially affect the widget build, dependency graph, Changesets enforcement, or package publishing behaviour.

Do not infer package relevance from commit messages.

Relevant symbols

- jobs.assistant-widget
- github.event_name
- github.event.pull_request.base.sha
- npx changeset status
- packages/assistant-widget/\*\*
- .changeset/\*\*
- package.json
- package-lock.json
- .github/workflows/test.yml
- .github/workflows/publish-assistant-widget.yml
- @redmoor/assistant-widget

Expected change surface

- Scope the Assistant widget PR CI job to changes that can affect the widget or its release process.
- Preserve all existing widget quality gates when the job is relevant.
- Preserve Changeset enforcement for widget/package changes.
- Avoid running the widget job for unrelated Admin/backend/documentation PRs.
- Ensure branch protection does not leave a permanently pending required check when the job is intentionally skipped.

Excluded areas

Do not:

- remove Assistant widget CI;
- remove Changeset enforcement;
- weaken widget lint, tests, build or package verification;
- change package publishing behaviour;
- change the Changesets Release PR workflow;
- modify @redmoor/assistant-widget behaviour;
- modify Admin or backend production code;
- add custom semantic-version logic;
- require all monorepo packages to run on every PR;
- use commit-message conventions to determine affected packages;
- introduce a bespoke dependency graph implementation when GitHub Actions/path filtering is sufficient.

Unknowns Codex must verify

Before implementation, verify:

- whether Tests / Assistant widget is currently configured as a required branch-protection check;
- how GitHub reports a workflow/job omitted by path filtering versus a job skipped via if:;
- whether filtering the workflow trigger itself would leave a required check permanently pending;
- whether job-level conditional execution is safer for current branch-protection settings;
- which root files materially affect Assistant widget installation, compilation or packaging;
- whether changes to npm workspace configuration require widget CI;
- whether changes to shared TypeScript, ESLint, Vite or test configuration outside packages/assistant-widget can affect the package;
- whether any shared source packages are imported by @redmoor/assistant-widget;
- whether .changeset/\*\* changes should run the full widget suite or only Changesets validation;
- whether .github/workflows/publish-assistant-widget.yml should be treated as a release-affecting input;
- whether .github/workflows/test.yml itself should cause the widget job to exercise its new configuration;
- whether the repository already contains a path-filtering dependency that should be reused.

Do not hard-code the proposed path list until the package’s actual dependency/configuration surface has been inspected.

⸻

Objective

Make Assistant widget CI proportional to the files affected by a pull request.

The current Tests / Assistant widget job runs on every pull request to main, even when the PR has no relationship to:

packages/assistant-widget

or its build/release infrastructure.

This creates unnecessary coupling between independent monorepo workstreams.

PR #81 demonstrates the problem: it modifies Admin UI files but is still blocked by the Assistant widget check.

The desired behaviour is:

- PRs affecting the Assistant widget or its relevant shared/release inputs run the complete Assistant widget CI job.
- PRs unrelated to the widget do not execute the expensive widget install/lint/test/build/package-verification pipeline.
- Changeset enforcement remains active when a publishable widget change requires release intent.
- Skipped widget work must not leave PRs blocked by a permanently pending required status check.

This is a CI-scoping change, not a reduction in package quality requirements.

Current architecture

.github/workflows/test.yml runs on every pull request and push targeting main.

The current Assistant widget job is unconditional:

jobs:
assistant-widget:
name: Assistant widget
runs-on: ubuntu-latest

It performs:

checkout full history
↓
setup Node
↓
npm ci
↓
changeset status
↓
lint widget
↓
test widget
↓
build widget
↓
pack:verify widget

The Changesets command is conditionally skipped only for the Changesets Release PR, but the entire Assistant widget job still runs for every other PR.

Therefore an Admin-only PR, backend-only PR or unrelated documentation PR incurs the complete widget pipeline.

PR #81 currently changes only:

- .codex/tasks/\*\*
- apps/admin/\*\*

It does not change:

- packages/assistant-widget/\*\*
- .changeset/\*\*
- root npm manifests
- widget publishing workflow

The Assistant widget check therefore provides little direct regression signal for that PR while still being capable of blocking it.

Required implementation

1. Add affected-path detection for Assistant widget CI

Determine whether a PR can materially affect @redmoor/assistant-widget.

At minimum investigate inclusion of:

packages/assistant-widget/\*\*

and repository-level inputs that directly affect the package, such as:

package.json
package-lock.json
.changeset/\*\*
.github/workflows/test.yml
.github/workflows/publish-assistant-widget.yml

Also include any verified shared configuration or source paths that the Assistant widget actually depends upon.

Do not automatically include all of:

apps/**
packages/**
\*\*

as that would defeat the purpose of this task.

The final path set must be justified by actual repository dependencies.

2. Skip expensive widget execution for unrelated PRs

When a pull request does not affect any Assistant widget-relevant path:

- do not run npm ci solely for the widget job;
- do not run widget lint;
- do not run widget tests;
- do not build the widget;
- do not run pack:verify;
- do not run widget Changesets enforcement.

PRs such as PR #81, containing only Admin UI/task-spec changes, must not execute the complete Assistant widget pipeline.

3. Preserve widget validation for relevant PRs

When a relevant path changes, preserve the current quality gates:

npm ci
npx changeset status --since=<pull-request-base-sha>
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

Do not weaken or remove these checks.

4. Preserve Changeset enforcement

A PR that modifies the publishable Assistant widget must continue to require valid release intent through Changesets where currently required.

The existing exception for the standard:

changeset-release/main

Release PR must continue to work.

Do not replace Changesets with custom package/version detection.

5. Handle required-check semantics correctly

This is a critical requirement.

Before choosing workflow-level paths, paths-ignore, job-level if:, or a dedicated path-filter job, verify how the repository’s branch protection currently treats:

Tests / Assistant widget

If this check is required, the implementation must not cause unrelated PRs to remain indefinitely blocked because GitHub never creates the expected status check.

Prefer an architecture where an intentionally irrelevant widget check resolves successfully/skipped in a way compatible with branch protection.

For example, if necessary:

detect changes
↓
widget relevant?
/ \
 yes no
↓ ↓
full job lightweight successful/no-op result

Do not implement trigger-level path filtering blindly if it breaks required-check behaviour.

6. Keep push-to-main behaviour appropriate

Inspect whether Assistant widget validation should remain broader on direct pushes/merges to main.

Pull-request scoping is the primary objective.

If push-to-main widget validation is part of release safety, preserve it unless repository evidence shows it is redundant.

Do not accidentally weaken the release path while optimising PR CI.

7. Do not make Admin/backend CI depend on widget state

An unrelated PR must not fail simply because:

- widget tests happen to be broken on its branch base;
- package verification has an unrelated defect;
- a pending Changeset exists for another widget change;
- package publishing infrastructure is temporarily unhealthy.

Those defects should block widget/release work, not independent Admin/backend PRs that cannot affect the package.

This task is specifically intended to reduce that cross-domain CI coupling.

8. Keep shared dependency changes protected

Do not scope the job only to:

packages/assistant-widget/\*\*

if root/shared files can break the package.

Examples that may need to trigger widget CI include verified changes to:

- workspace dependency resolution;
- lockfile;
- root npm scripts used by package CI;
- shared TypeScript configuration;
- shared ESLint configuration;
- shared Vite configuration;
- shared source packages imported by the widget;
- Changesets configuration;
- release workflow configuration.

Codex must inspect actual package references and include only relevant shared inputs.

9. Prefer declarative GitHub Actions configuration

Use native workflow expressions/path filtering or an established maintained filtering action where needed.

Avoid introducing a custom Node/Python/Bash program that independently computes changed package dependencies unless native filtering cannot satisfy the branch-protection requirements.

Keep the resulting CI configuration understandable from .github/workflows/test.yml.

10. Document CI scope where appropriate

If existing documentation describes Assistant widget CI, update it to explain:

- widget checks run for widget/release-affecting changes;
- unrelated monorepo PRs do not run the package pipeline;
- relevant shared dependency changes still trigger widget validation;
- Changesets enforcement remains part of widget PR validation.

Do not add standalone documentation solely to explain obvious YAML unless repository conventions require it.

Acceptance criteria

- PRs modifying packages/assistant-widget/\*\* run Tests / Assistant widget.
- Relevant shared/root dependency changes run the Assistant widget checks.
- Widget release/Changesets configuration changes trigger appropriate validation.
- Widget PRs still run lint.
- Widget PRs still run tests.
- Widget PRs still run build.
- Widget PRs still run pack:verify.
- Widget package changes still enforce Changesets.
- The standard changeset-release/main PR remains compatible with CI.
- A PR changing only apps/admin/\*\* does not run the expensive Assistant widget pipeline.
- A PR changing only backend files does not run the expensive Assistant widget pipeline unless a verified shared dependency requires it.
- A task/documentation-only PR does not run the expensive Assistant widget pipeline unless the changed file affects widget CI/release configuration.
- PR #81’s current changed-file set would be classified as not affecting the Assistant widget.
- An intentionally skipped widget pipeline does not leave branch protection waiting indefinitely for a missing required check.
- Existing branch-protection semantics remain usable.
- Push/release safety is not weakened accidentally.
- No custom semantic-version or Changesets replacement logic is introduced.
- No widget production code change is required.
- CI configuration remains understandable and maintainable.

Tests to add or update

Validate path-selection behaviour with representative changed-file sets.

At minimum verify these cases.

Widget source change

Example:

packages/assistant-widget/src/AssistantWidget.tsx

Expected:

Assistant widget CI runs.

Widget package manifest change

Example:

packages/assistant-widget/package.json

Expected:

Assistant widget CI runs.

Root dependency change

Example:

package-lock.json

Expected:

Assistant widget CI runs.

Changeset change

Example:

.changeset/example.md

Expected:

Relevant Changesets/widget validation runs according to the selected architecture.

Admin-only PR

Example:

apps/admin/src/features/operations/Operations.tsx
apps/admin/src/api/adminApi.ts
.codex/tasks/13g-admin-operations-ui.md

Expected:

Expensive Assistant widget CI does not run.

Backend-only PR

Example:

apps/backend/operations/api/router.py

Expected:

Assistant widget CI does not run unless repository inspection proves a direct dependency.

Release workflow change

Example:

.github/workflows/publish-assistant-widget.yml

Expected:

Assistant widget/release validation runs.

CI workflow change

Example:

.github/workflows/test.yml

Expected:

The changed configuration is exercised sufficiently to avoid merging an unvalidated CI change.

Where GitHub Actions path logic cannot be conveniently unit-tested, validate the workflow syntax and manually reason/test representative PR changed-file sets using existing repository tooling.

Do not create a large custom test framework merely to test YAML expressions.

Verification commands

git diff --check
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
npx changeset status

Validate the modified workflow YAML with an existing parser/tool available in the repository or development environment.

Inspect the final workflow and verify the following matrix:

## Change Widget CI

packages/assistant-widget/** RUN
widget-relevant root/shared config RUN
package-lock.json RUN
.changeset/** RUN/VALIDATE
widget release workflow RUN/VALIDATE
apps/admin/** only SKIP
apps/backend/** only SKIP
unrelated docs/tasks only SKIP

Also verify the actual branch-protection/status-check behaviour on a pull request whose changes are unrelated to the Assistant widget.

The task is not complete if an unrelated PR still executes the full Assistant widget package pipeline or becomes blocked because the expected required check never resolves.
