PR 12H — Path-Scoped Admin UI CI

Repository state

Expected branch:

12h-path-scoped-admin-ui-ci

Create this as a new branch from the latest:

origin/main

Base branch:

main

Worktree:

Frontend

Dependencies:

- Existing apps/admin application
- Existing Admin test/lint/typecheck/build scripts
- Existing GitHub Actions general Tests workflow
- Existing path-scoped Assistant Widget CI workflow
- PR 12G — Path-Scoped Assistant Widget CI Checks
- Existing Storybook configuration for Admin
- Existing root npm workspace/install configuration

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/12g-path-scoped-assistant-widget-ci.md
- .github/workflows/test.yml
- .github/workflows/test-assistant-widget.yml
- apps/admin/package.json
- apps/admin/README.md
- root package.json
- root package-lock.json
- root TypeScript configuration files used by apps/admin
- Admin Vite configuration
- Admin Storybook configuration
- Admin ESLint configuration
- packages/assistant-widget/package.json

Inspect the current Admin dependency graph before finalising workflow trigger paths.

Primary change area

- New dedicated Admin CI workflow under .github/workflows/
- Existing general .github/workflows/test.yml only if Admin validation is currently duplicated there
- apps/admin/README.md where CI behaviour should be documented
- Repository CI verification tooling only if an existing reusable mechanism already exists

Canonical implementation examples

Use the dedicated Assistant Widget workflow as the primary architectural example:

.github/workflows/test-assistant-widget.yml

The Admin workflow should follow the same principle:

Pull request
↓
GitHub evaluates Admin-relevant paths
↓
Admin affected?
/ \
 yes no
↓ ↓
Admin no Admin workflow
CI no Admin check
↓
npm ci
test
lint
typecheck
build
build-storybook

The presence of the Admin CI status must mean the full Admin validation pipeline actually ran.

Do not add:

- runtime path-detection jobs
- no-op Admin jobs
- detector-only status checks
- always-successful placeholder jobs

Relevant symbols

- .github/workflows/test.yml
- .github/workflows/test-assistant-widget.yml
- proposed .github/workflows/test-admin.yml
- pull_request.paths
- push
- apps/admin/\*\*
- packages/assistant-widget/\*\*
- package.json
- package-lock.json
- root TypeScript configuration
- Admin ESLint configuration
- Admin Vite configuration
- Admin Storybook configuration
- npm test
- npm run lint
- npm run typecheck
- npm run build
- npm run build-storybook

Expected change surface

Expected changes include:

- Add a dedicated Admin UI GitHub Actions workflow.
- Scope Admin CI to files capable of affecting apps/admin.
- Run the full required Admin validation suite whenever the workflow appears.
- Keep unrelated PRs free from misleading Admin CI checks.
- Preserve existing backend and Assistant Widget workflows.
- Ensure Admin dependency changes outside apps/admin/\*\* are included where they can break Admin.

Excluded areas

Do not:

- modify Admin production UI behaviour
- modify backend production code
- modify Assistant Widget production code
- remove or weaken Admin tests
- remove lint
- remove type checking
- remove production build verification
- remove Storybook build verification
- add runtime relevance filtering
- add a separate Admin affected job
- add a no-op success check for unrelated PRs
- run Admin CI for all repository changes without verifying that this is necessary
- duplicate Admin verification across multiple workflows without a concrete reason
- modify release/publishing behaviour
- change package versions or Changesets behaviour
- change unrelated CI jobs

Unknowns Codex must verify

Before implementation, verify:

- whether any existing workflow already runs some or all Admin checks
- whether those checks should move to the dedicated Admin workflow or remain where they are
- exact root/shared files imported or inherited by apps/admin
- whether packages/assistant-widget/\*\* must trigger Admin CI because Admin imports @redmoor/assistant-widget
- whether other workspace packages are direct Admin dependencies
- which root tsconfig files affect Admin typechecking/build
- which ESLint configuration files affect Admin linting
- which Vite configuration files affect Admin build
- which Storybook configuration files affect Admin Storybook build
- whether root package.json changes can affect Admin
- whether package-lock.json changes must trigger Admin CI
- whether changes to the Admin workflow itself should trigger Admin CI
- whether changes to shared GitHub Actions helpers affect this workflow
- whether Admin CI should run on pushes to main
- whether a global required branch-protection rule would block unrelated PRs when the path-scoped Admin workflow is absent
- exact workflow/job names that GitHub will expose as status checks
- whether Storybook tests currently run elsewhere and whether they are distinct from npm run build-storybook

Do not finalize the paths: list until the actual Admin dependency/configuration surface has been inspected.

⸻

Objective

Introduce a dedicated, path-scoped GitHub Actions workflow for the Admin UI.

When a pull request can affect:

apps/admin

GitHub must run the complete Admin quality gate:

npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook

from the Admin workspace.

When a pull request cannot affect Admin, the Admin workflow must not run and an Admin-specific status check must not appear.

The desired semantics are:

Admin-relevant PR
→ Admin CI appears
→ complete Admin validation runs
→ validation must pass
Unrelated PR
→ Admin CI absent
→ no misleading successful Admin check

This should follow the same domain-specific CI model already established for the Assistant Widget.

Current architecture

The repository already has a dedicated path-scoped Assistant Widget workflow:

.github/workflows/test-assistant-widget.yml

That workflow uses GitHub Actions workflow-level paths: filtering rather than executing a relevance detector on every pull request.

The repository also has a general Tests workflow that currently runs backend and Storybook-oriented validation.

Admin has its own package scripts in:

apps/admin/package.json

including:

{
"build": "tsc -b && vite build",
"lint": "eslint .",
"typecheck": "tsc -b",
"test": "vitest run",
"build-storybook": "storybook build"
}

The Admin feature specifications already treat these commands as the required completion gate.

However, they are not currently represented as a dedicated Admin CI boundary.

This means an Admin pull request can reach review without objective CI evidence that all required Admin checks passed.

The repository should model Admin as its own independently validated frontend deliverable.

Required implementation

1. Add a dedicated Admin CI workflow

Create a dedicated GitHub Actions workflow, preferably:

.github/workflows/test-admin.yml

Use a clear workflow name such as:

name: Admin UI CI

Use a clear job name such as:

name: Admin validation

The exact names must be documented if branch protection depends on them.

Do not add Admin validation as another always-present job inside the generic Tests workflow unless repository inspection proves a dedicated workflow is technically unsuitable.

2. Path-scope Admin pull-request execution

Configure:

on:
pull_request:
branches: - main
paths:
...

The final path list must reflect the real Admin dependency graph.

At minimum inspect and consider:

apps/admin/**
packages/assistant-widget/**
package.json
package-lock.json
tsconfig\*.json
.github/workflows/test-admin.yml

Also include any verified shared configuration files that can affect:

- Admin TypeScript compilation
- Admin lint
- Vite build
- Storybook build
- workspace dependency resolution

Do not include broad paths such as:

apps/**
docs/**
.codex/tasks/\*\*
\*\*

unless repository inspection establishes that they genuinely affect Admin.

3. Include Assistant Widget as an Admin dependency where appropriate

The Admin client currently imports:

@redmoor/assistant-widget

Codex must verify whether source/workspace changes in:

packages/assistant-widget/\*\*

can change Admin’s compilation or runtime build output.

If yes, include that path in Admin CI triggers.

The desired result is:

Assistant Widget change
→ Assistant Widget CI runs
→ Admin CI also runs if Admin can be broken by that dependency

That is not duplication: each workflow validates a different deliverable.

Do not include the widget path merely by assumption; verify the dependency relationship first.

4. Run the complete Admin verification pipeline

When Admin CI triggers, it must run all required validation.

Use repository-consistent Node setup.

Expected structure:

- name: Check out repository
  uses: actions/checkout@v4
- name: Set up Node
  uses: actions/setup-node@v4
  with:
  node-version: '24'
  cache: npm
  cache-dependency-path: package-lock.json
- name: Install dependencies
  run: npm ci

Then execute the Admin checks.

Prefer running them from:

cd apps/admin

or use npm workspace commands where the repository’s conventions make that cleaner.

The workflow must run the equivalents of:

npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook

against apps/admin.

All five checks are mandatory.

5. Keep the check cohesive

Prefer one Admin validation job containing sequential steps rather than five unrelated required jobs.

Desired GitHub semantics:

Admin UI CI / Admin validation

The job’s step list should make the failing gate obvious.

For example:

Install dependencies
Test Admin
Lint Admin
Typecheck Admin
Build Admin
Build Admin Storybook

Do not deliberately collapse all checks into one opaque shell command if individual named workflow steps provide clearer failure reporting.

6. Do not hide failures behind continue-on-error

None of the required Admin gates may use:

continue-on-error: true

A failure in any of:

- tests
- lint
- typecheck
- production build
- Storybook build

must fail Admin CI.

Do not use shell constructs that mask command failure.

7. Preserve complete validation when relevant

Do not skip individual Admin steps based on runtime file detection.

Once GitHub has determined that the workflow is relevant, the complete Admin pipeline must run.

For example:

Admin CSS-only change
→ full Admin test/lint/typecheck/build/Storybook pipeline
Admin test-only change
→ full Admin pipeline
Admin workflow change
→ full Admin pipeline

The check means the Admin deliverable was validated, not merely the files that appear directly related to one individual command.

8. Avoid misleading checks on unrelated PRs

An unrelated backend-only PR must not display a successful Admin CI check where none of the Admin validation actually ran.

An unrelated documentation/task-only PR must not display Admin CI.

Use workflow-level paths to achieve this.

Do not implement:

Admin affected?
✓

or:

Admin CI
✓ skipped all meaningful steps

The Admin-specific check must be absent when Admin is unaffected.

9. Verify branch protection / required-check semantics

Inspect repository branch protection or rulesets before completion.

If the proposed Admin check is configured as globally required, unrelated PRs may become permanently blocked because a path-scoped workflow intentionally does not run.

The desired state is:

Admin-relevant PR:
Admin CI exists and must pass where repository protection supports this.
Unrelated PR:
Admin CI does not exist and merge is not blocked waiting for it.

Do not add a fake success job merely to satisfy globally required-check semantics.

If the repository cannot conditionally require path-scoped workflows, document the exact repository configuration implication rather than reintroducing misleading checks.

10. Preserve existing backend CI

Do not remove, weaken or rename backend tests solely as part of this task.

The general Tests workflow should continue to own backend validation unless repository inspection proves another existing architecture.

11. Preserve Assistant Widget CI

Do not alter the semantics established by:

.github/workflows/test-assistant-widget.yml

unless a minimal path-list adjustment is required because a shared file is discovered during dependency inspection.

This task does not replace or merge the Widget workflow.

Final conceptual CI boundaries should be:

Backend
→ backend validation
Assistant Widget
→ widget package validation
Admin UI
→ Admin application validation

Each should represent its own deliverable.

12. Determine Storybook test vs Storybook build responsibility

The repository currently has a Storybook test job in the general Tests workflow.

Codex must verify:

- what project(s) that job validates
- whether it already covers Admin stories
- whether it is a browser interaction test rather than a static Storybook build
- whether keeping both is necessary

Regardless of that result, the Admin CI workflow must still run:

npm run build-storybook

because PR 13G and related Admin specs explicitly require a successful Admin Storybook build.

Do not remove existing Storybook tests merely because Admin now builds Storybook.

13. Preserve push-to-main validation

Determine whether Admin CI should also run on relevant pushes to:

main

Preferred structure:

push:
branches: - main
paths: - <same verified Admin-impacting paths>

If the repository intentionally validates all main pushes differently, preserve that architecture.

Do not weaken post-merge confidence for Admin simply to optimize pull-request execution.

14. Update Admin CI documentation

Update:

apps/admin/README.md

or the repository’s canonical CI documentation.

Document:

- Admin has a dedicated CI workflow.
- Admin CI is path-scoped.
- The workflow appears only for Admin-impacting changes.
- When it appears, it runs the full Admin quality gate.
- The gate consists of tests, lint, typecheck, build, and Storybook build.
- Shared dependency changes may trigger more than one domain workflow.
- Unrelated PRs do not receive a misleading Admin status.

15. Verify path behaviour

Verify the workflow against a trigger matrix.

Do not consider the task complete from YAML inspection alone.

Where practical, use actual PR/workflow evidence.

At minimum reason against and test the following cases using repository tooling or a deterministic workflow verification script if an existing pattern is available.

Acceptance criteria

- A dedicated Admin UI GitHub Actions workflow exists.
- The Admin workflow is separate from the Assistant Widget workflow.
- The Admin workflow is separate from backend validation.
- Pull-request Admin CI is scoped using workflow-level paths:.
- No runtime Admin relevance detector is introduced.
- No no-op Admin success job is introduced.
- An Admin source change triggers Admin CI.
- An Admin test change triggers Admin CI.
- An Admin Storybook change triggers Admin CI.
- An Admin package/config change triggers Admin CI.
- Root package-lock.json changes trigger Admin CI.
- Root package.json changes trigger Admin CI where verified relevant.
- Root/shared TypeScript config changes trigger Admin CI where verified relevant.
- Shared lint/build/Storybook config changes trigger Admin CI where verified relevant.
- Changes to the Admin CI workflow itself trigger Admin CI.
- packages/assistant-widget/\*\* triggers Admin CI if verified as an Admin build dependency.
- Backend-only changes do not trigger Admin CI unless they modify a verified shared Admin dependency.
- Documentation/task-only changes do not trigger Admin CI.
- When Admin CI appears, repository checkout actually runs.
- When Admin CI appears, npm ci actually runs.
- When Admin CI appears, Admin tests actually run.
- When Admin CI appears, Admin lint actually runs.
- When Admin CI appears, Admin typecheck actually runs.
- When Admin CI appears, Admin production build actually runs.
- When Admin CI appears, Admin Storybook build actually runs.
- Failure of any required Admin command fails the Admin CI job.
- No required Admin command uses continue-on-error.
- Existing backend validation remains intact.
- Existing Assistant Widget CI semantics remain intact.
- Existing Storybook tests remain intact unless a justified non-duplicative change is documented.
- Admin CI runs on relevant main pushes where required by the repository’s verification model.
- Branch protection does not leave unrelated PRs waiting for an intentionally absent Admin check.
- Admin CI documentation is updated.
- No Admin production source changes are required.

Tests to add or update

Validate the trigger matrix below.

Admin source change

Changed file:

apps/admin/src/App.tsx

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Admin test change

Changed file:

apps/admin/src/App.test.tsx

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Admin Storybook change

Changed file:

apps/admin/src/features/operations/Operations.stories.tsx

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Admin package manifest

Changed file:

apps/admin/package.json

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Root lockfile

Changed file:

package-lock.json

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Root package manifest

Changed file:

package.json

Expected after dependency verification:

Admin UI CI: PRESENT

if root package/workspace configuration can affect Admin.

Assistant Widget source

Changed file:

packages/assistant-widget/src/AssistantWidget.tsx

Expected after dependency verification:

Assistant Widget CI: PRESENT
Admin UI CI: PRESENT

if Admin is compiled against the workspace Widget source/package.

Backend-only change

Changed file:

apps/backend/operations/api/router.py

Expected:

Admin UI CI: ABSENT

unless repository inspection identifies a concrete generated/shared dependency.

Task-only change

Changed file:

.codex/tasks/example.md

Expected:

Admin UI CI: ABSENT

Documentation-only change

Changed file:

docs/example.md

Expected:

Admin UI CI: ABSENT

Admin workflow change

Changed file:

.github/workflows/test-admin.yml

Expected:

Admin UI CI: PRESENT
Full Admin validation: RUN

Required command failure

Temporarily or deterministically validate failure propagation for the workflow configuration where repository tooling supports it.

Expected:

test failure → Admin CI fails
lint failure → Admin CI fails
typecheck failure → Admin CI fails
build failure → Admin CI fails
build-storybook failure → Admin CI fails

Do not commit intentional failures solely to test this behaviour if existing workflow/tooling provides a safer verification method.

Verification commands

First run the exact Admin quality gate locally:

cd apps/admin
npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook

Also run:

git diff --check

Validate modified workflow YAML using an existing YAML parser or repository workflow-verification utility.

Inspect the resulting workflow structure and confirm conceptually:

.github/workflows/test-admin.yml
pull_request:
branches: - main
paths: - verified Admin-impacting paths
push:
branches: - main
paths: - verified Admin-impacting paths
jobs:
admin:
checkout
setup node
npm ci
test
lint
typecheck
build
build-storybook

Confirm:

.github/workflows/test-assistant-widget.yml

still owns Assistant Widget validation.

Confirm:

.github/workflows/test.yml

still owns the intended repository-wide/backend checks and does not contain a redundant full Admin validation job.

Finally verify live or equivalent GitHub behaviour:

Admin-relevant PR
→ Admin UI CI appears
→ every required Admin step actually runs
→ check passes only if all steps pass
Unrelated PR
→ Admin UI CI absent
→ PR is not blocked waiting for the absent check

Do not report the task complete if an unrelated PR still produces a successful Admin-specific status where the Admin validation pipeline did not run.
