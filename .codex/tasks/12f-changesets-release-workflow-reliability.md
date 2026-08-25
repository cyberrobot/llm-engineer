PR 12F — Changesets Release Workflow Reliability

Repository state

Expected branch:

feature/12f-changesets-release-workflow-reliability

Base branch:

main

Worktree:

Frontend

Dependencies:

- PR 12E — Assistant Package Structure and Standard Changesets Release Workflow
- Existing @redmoor/assistant-widget package
- Existing Changesets configuration
- Existing changesets/action workflow
- Existing npm Trusted Publishing / GitHub OIDC configuration
- Existing widget package verification

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/12e-assistant-package-structure-and-changesets-release.md
- .codex/tasks/12e-assistant-package-structure-and-changesets-release-review1.md
- .github/workflows/publish-assistant-widget.yml
- .github/workflows/test.yml
- .changeset/config.json
- .changeset/\*.md
- package.json
- packages/assistant-widget/package.json
- packages/assistant-widget/README.md

Primary change area

- .github/workflows/publish-assistant-widget.yml
- .changeset/
- Root release scripts/configuration where required
- packages/assistant-widget/README.md
- Release documentation where required

Canonical implementation examples

Use established release tooling rather than custom orchestration.

Preferred tooling:

- @changesets/cli
- changesets/action
- actions/checkout
- actions/setup-node
- npm Trusted Publishing with GitHub OIDC

Preserve the standard Changesets Release PR model:

Package PR + Changeset
↓
Merge to main
↓
changesets/action
↓
Create/update Release PR
↓
Human reviews and merges Release PR
↓
changesets/action
↓
Publish package + create release/tag

Relevant symbols

- @redmoor/assistant-widget
- .github/workflows/publish-assistant-widget.yml
- changesets/action@v1
- npm run release
- changeset publish
- .changeset/config.json
- workflow_dispatch
- github.ref
- refs/heads/main
- GITHUB_TOKEN
- npm Trusted Publishing
- id-token: write

Expected change surface

- Diagnose the currently failing Release assistant widget / Verify and release workflow.
- Fix the root cause preventing the standard Changesets workflow from completing successfully.
- Ensure pending Changesets can create or update a Release PR.
- Ensure merging a Changesets Release PR can publish the package.
- Preserve manual workflow_dispatch as an optional invocation of the same workflow.
- Preserve the human approval boundary at the Release PR merge.

Excluded areas

- Converting publishing to a manual-only release process
- Direct manual npm publishing
- Manually incrementing package versions
- Manually creating release tags
- Custom semantic-version calculation
- semantic-release
- release-it
- Conventional Commit based releases
- Backend functionality
- Admin functionality
- Widget UI functionality
- Unrelated CI failures
- Long-lived npm authentication tokens

Unknowns Codex must verify

Before changing code, inspect the repository and the latest failed GitHub Actions execution for:

Release assistant widget / Verify and release

Determine the exact failed step and root cause.

Codex must verify rather than assume:

- whether failure occurs during dependency installation;
- lint;
- tests;
- build;
- package verification;
- changesets/action;
- Release PR creation/update;
- npm publication;
- GitHub Release/tag creation;
- GitHub token permissions;
- npm Trusted Publishing / OIDC authentication;
- Changesets state detection;
- repository or branch protection behaviour;
- absence/presence of an existing Changesets Release PR;
- whether the pending Changeset on main is valid and discoverable;
- whether changesets/action is attempting publication when it should instead create/update a Release PR;
- whether the current workflow configuration matches the current supported Changesets Trusted Publishing approach.

Do not modify release behaviour until the failing workflow logs identify the actual failure.

⸻

Objective

Restore a reliable standard Changesets release workflow for @redmoor/assistant-widget.

A normal merge to main must be able to run the release workflow without producing an unexplained failing Verify and release job.

When unreleased Changesets exist, the workflow must successfully create or update the Changesets Release PR.

When the Release PR is reviewed and merged, the same workflow must publish the new package version and create the corresponding release/tag.

The workflow must retain the human-controlled Release PR merge as the release approval boundary.

Do not change the repository to direct or manual-only publishing merely to eliminate the failing workflow.

Current architecture

PR 12E introduced the standard Changesets workflow.

The current release workflow runs on:

on:
push:
branches: - main
workflow_dispatch:

The release job is restricted to:

if: github.ref == 'refs/heads/main'

Before running Changesets, it performs:

- npm ci
- widget lint
- widget tests
- widget build
- package verification

The release step currently uses:

uses: changesets/action@v1
with:
publish: npm run release
createGithubReleases: true

The root release command is:

"release": "changeset publish"

Changesets is configured for main, public packages and normal workspace versioning.

A pending Changeset currently exists for:

@redmoor/assistant-widget

The intended architecture remains:

1. Feature PR contains a Changeset.
2. Feature PR merges to main.
3. changesets/action creates or updates a Release PR.
4. Release PR is reviewed manually.
5. Release PR merges.
6. changesets/action publishes the package.
7. GitHub/npm release metadata is created automatically.

workflow_dispatch is a recovery/manual invocation of this same process. It is not a separate direct-publish mechanism.

Required implementation

1. Diagnose the failing workflow first

Inspect the latest failed:

Release assistant widget / Verify and release

run on main.

Record the exact failing job step in the implementation notes or PR description.

Identify the actual root cause before changing configuration.

Do not infer the cause solely from the workflow YAML.

If failure is external configuration rather than repository code — for example npm Trusted Publishing configuration — document the exact required configuration and make only repository changes necessary to support it.

2. Preserve the Changesets Release PR model

Do not remove the push trigger from main merely to silence the failure.

The repository must continue automatically invoking Changesets after merges to main.

When pending Changesets exist:

changesets/action must create or update a Release PR.

It must not immediately publish the package merely because an ordinary feature PR was merged.

Publishing must happen only once Changesets has produced versioned release state through the Release PR and that PR has been merged.

3. Make Release PR creation reliable

Verify that the workflow has the permissions and configuration required for changesets/action to create and update its Release PR.

Preserve least-privilege permissions while allowing the required behaviour.

Expected permissions include only what is necessary, such as:

permissions:
contents: write
pull-requests: write
id-token: write

If additional or different permissions are necessary, justify them from the action’s actual requirements.

Do not use a personal access token unless GitHub’s built-in token genuinely cannot support the required workflow and the repository’s constraints explicitly require an alternative.

4. Make publication reliable

After a Changesets Release PR is merged, the workflow must be capable of:

- running all package gates;
- determining the pending package version;
- publishing @redmoor/assistant-widget;
- publishing with public access;
- using npm Trusted Publishing;
- using OIDC rather than a long-lived npm token;
- retaining provenance;
- creating the expected GitHub release/tag.

Do not bypass Changesets by calling npm publish directly from custom conditional logic.

5. Keep workflow_dispatch

Retain:

workflow_dispatch:

Manual invocation must:

- execute the same release workflow;
- be restricted to main;
- run the same verification gates;
- run the same changesets/action;
- create/update a Release PR when Changesets are pending;
- publish only when the repository is already in the post-Release-PR state expected by Changesets.

Do not implement a second manual publication path.

6. Prevent unrelated changes from creating misleading release failures

A merge to main that does not modify the widget may still invoke the Changesets workflow. That is acceptable.

However:

- the workflow must exit successfully when there is no release work to perform;
- the absence of a publishable release must not be treated as an error;
- unrelated backend/admin merges must not cause a red release check solely because no widget release is required.

Do not solve this with custom semantic package-change detection if standard Changesets already handles the no-release state.

7. Handle the currently pending Changeset correctly

Inspect the current pending .changeset/\*.md file.

Verify that it:

- references @redmoor/assistant-widget;
- contains a valid semantic release type;
- is discoverable by changeset status;
- can be consumed into the Release PR;
- is removed/consumed by the normal Changesets versioning lifecycle rather than manually deleted to make CI green.

Do not manually bump packages/assistant-widget/package.json merely to recover the workflow.

8. Preserve package quality gates

Keep all release safety gates before the Changesets action:

npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

Do not weaken these checks to make the release workflow pass.

If one of these gates is the actual failure, fix the underlying package defect rather than skipping the check.

9. Avoid duplicate CI responsibilities where practical

The normal test workflow already validates the widget.

Do not introduce additional duplicated release-specific test suites.

The release workflow should retain the publication safety gates required immediately before release, but avoid custom validation logic that duplicates Changesets or the normal package tests.

10. Document the release lifecycle clearly

Update the package/release documentation where necessary so it explicitly distinguishes:

Automatic workflow invocation

A push to main invokes Changesets automatically.

Manual release approval

A human reviews and merges the Changesets Release PR.

Automatic publication

After the Release PR merges, Changesets publishes automatically.

Manual recovery invocation

workflow_dispatch runs the same workflow from main.

Do not describe the package as being manually published.

11. Recovery behaviour

Document or implement safe recovery for a failed workflow.

A failed invocation must be safely rerunnable without:

- publishing the same package version twice;
- producing duplicate release tags;
- creating multiple competing Release PRs;
- corrupting pending Changesets;
- requiring manual version edits.

Prefer the idempotent behaviour already provided by Changesets and npm over custom recovery logic.

Acceptance criteria

- The root cause of the current Verify and release failure is identified from the actual GitHub Actions run.
- The fix addresses that root cause rather than merely suppressing the workflow.
- The release workflow continues running on pushes to main.
- workflow_dispatch remains available.
- The release job can execute only from refs/heads/main.
- Pending Changesets cause changesets/action to create or update one Release PR.
- An ordinary feature merge does not directly publish a package before the Release PR is merged.
- The Release PR remains the human approval boundary.
- Merging the Release PR causes the package to publish automatically.
- @redmoor/assistant-widget is published through changeset publish.
- No custom semantic-version calculation is introduced.
- No manual package-version bump is required.
- No manual Git tag is required.
- npm Trusted Publishing is preserved.
- GitHub OIDC is preserved.
- npm provenance is preserved.
- No long-lived npm token is introduced.
- Widget lint runs before release handling.
- Widget tests run before release handling.
- Widget build runs before release handling.
- Package verification runs before release handling.
- A run with no pending release work exits successfully.
- Unrelated merges to main do not cause a release failure merely because no widget publication is necessary.
- Re-running a failed workflow does not create duplicate versions, Release PRs, releases or tags.
- The existing pending Changeset is processed through the normal Changesets lifecycle.
- Documentation accurately describes Release PR approval versus automatic workflow execution.
- All existing relevant CI checks continue to pass.

Tests to add or update

Do not attempt to reproduce GitHub Actions itself in unit tests.

Add or update repository-level validation where practical for:

- release workflow YAML validity;
- Changesets configuration validity;
- pending Changeset validity;
- package release command availability;
- widget package verification;
- changeset status;
- documentation expectations if existing repository tests cover workflow configuration.

Important cases to verify:

1. Pending Changeset
   changeset status recognises @redmoor/assistant-widget.
2. No pending release
   The workflow/action path does not fail merely because there is nothing to release.
3. Release PR lifecycle
   Pending Changesets are versioned through the Changesets Release PR rather than direct publication.
4. Manual invocation
   workflow_dispatch cannot execute the release job from a non-main ref.
5. Package gates
   A lint, test, build or package verification failure prevents release handling.
6. Trusted Publishing
   Publishing does not depend on NPM_TOKEN or another long-lived npm token.
7. Idempotent retry
   Re-running after a recoverable workflow failure does not create duplicate release state.

Do not add tests for internal behaviour already owned by changesets/action.

Verification commands

npm ci
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
npx changeset status
git diff --check

Also:

# Parse/validate the modified GitHub Actions YAML using an existing

# repository dependency/tool where available.

Before declaring the task complete, inspect the resulting workflow and verify:

push to main
↓
quality gates
↓
changesets/action
↓
pending Changesets?
/ \
 yes no
↓ ↓
Release PR success/no-op
↓
human merge
↓
quality gates
↓
changesets/action
↓
publish + release/tag

Finally, verify the fixed workflow against GitHub Actions on main.

The task is not complete if the repository changes look correct locally but the relevant Release assistant widget / Verify and release GitHub Actions execution still fails.
