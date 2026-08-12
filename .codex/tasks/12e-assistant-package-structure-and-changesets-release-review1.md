# PR 12E Review Fixes — Release Safety and Changeset Enforcement

## Repository state

Expected branch: `feature/12e-assistant-package-publishing`

Base branch: `main`

Pull request: #73

Reviewed head: `4447a7513330d49c5fbce61b8d5db2b369860476`

Governing specification:

- `.codex/tasks/12e-assistant-package-structure-and-changesets-release.md`

Do not create a new branch. Do not reimplement the completed package move, public API preservation,
package verification, or standard Changesets release flow.

## Review outcome

PR #73 substantially implements PR 12E, but it is not approvable in its reviewed state.

The review found these PR-owned gaps:

1. `workflow_dispatch` can be started from a non-`main` ref. The release job must never create a
   Release PR or publish from an unmerged branch or tag.
2. Pull-request CI does not enforce the requirement that a change to the publishable widget has a
   Changeset. The current PR contains a Changeset, but the repository does not protect the rule for
   subsequent package changes.
3. `docs/architecture/repository-map.md` still says that the npm workspace contains only `apps/*`,
   which contradicts the implemented `apps/*` and `packages/*` workspace layout.

The failing Backend tests check observed on the reviewed head is not caused by PR #73. The failure is
in an operations-administration audit assertion, while the PR changes no backend files. Do not alter
backend behaviour as part of this review fix. The check must still pass on a rerun before approval.

## Required implementation

### 1. Restrict the release workflow to `main`

Keep `workflow_dispatch`, but guard the release job so it only runs when `github.ref` is
`refs/heads/main`.

The manual trigger must use the same Changesets action, package gates, OIDC permissions, and publish
command as the push-to-`main` flow. Do not add another release path or custom publication logic.

Document that a manually dispatched release must select `main`; non-`main` refs must not execute the
release job.

### 2. Enforce Changesets and package checks in pull-request CI

Add an Assistant widget job to the existing test workflow that:

- checks out full Git history so Changesets can compare against the pull-request base;
- installs the locked npm dependency graph using the repository's Node version and npm cache;
- on pull requests, runs `changeset status` against the exact pull-request base SHA;
- runs widget lint, tests, build, and `pack:verify`.

Use `@changesets/cli`; do not duplicate its package-change detection or semantic-version rules in a
custom script.

The Changesets status check may be pull-request-only because a merged Changesets Release PR has
already consumed its release intent before the resulting push-to-`main` workflow runs.

### 3. Correct workspace and release documentation

Update the repository map to state that npm workspaces include both `apps/*` and `packages/*`.

Update the widget release documentation with the safe `workflow_dispatch` ref requirement. Preserve
the existing documentation for Release PRs, npm Trusted Publishing, OIDC, provenance, recovery, and
automatic tags.

## Excluded areas

- Backend implementation and backend tests
- Widget UI behaviour or public exports
- Admin and RAG UI behaviour
- Package versions, changelog contents, and release tags
- Custom release orchestration or semantic-version logic
- Commit, push, or pull-request metadata changes

## Acceptance criteria

- [ ] The Changesets release job can execute only from `refs/heads/main`.
- [ ] `workflow_dispatch` remains available and uses the standard Changesets flow.
- [ ] Pull-request CI fails when a publishable widget change has no Changeset.
- [ ] Pull-request CI runs widget lint, tests, build, and package verification.
- [ ] The check compares against the exact pull-request base commit with sufficient Git history.
- [ ] The repository map documents both npm workspace roots.
- [ ] The package README documents that manual release runs must select `main`.
- [ ] No backend change is introduced for the unrelated failed check.
- [ ] Relevant local checks pass.
- [ ] PR #73's required GitHub checks pass on the amended head before approval.

## Verification commands

```sh
npx changeset status --since=origin/main
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
git diff --check
```

Also parse the modified workflow YAML with an available local parser and inspect the final diff.
