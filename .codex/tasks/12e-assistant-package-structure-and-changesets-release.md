# PR 12E — Assistant Package Structure and Standard Changesets Release Workflow

## Repository state

Expected branch: `feature/12e-assistant-package-publishing`

Base branch: `main`

Worktree: Frontend

Dependencies:

- Existing `@redmoor/assistant-widget` package
- Existing widget build/test/package verification
- Existing GitHub Actions configuration
- Existing npm Trusted Publishing configuration

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `package.json`
- `package-lock.json`
- `apps/assistant/package.json`
- `apps/assistant/README.md`
- `.github/workflows/publish-assistant-widget.yml`
- `.codex/tasks/12d-widget-release-automation.md`

### Primary change area

- `packages/assistant-widget/`
- `apps/assistant-demo/`
- `.changeset/`
- `.github/workflows/`
- Root `package.json`
- Root `package-lock.json`
- Documentation

### Canonical implementation examples

Use established tooling rather than bespoke release logic.

Preferred tooling:

- `@changesets/cli`
- `changesets/action`
- `actions/checkout`
- `actions/setup-node`

### Relevant symbols

- `@redmoor/assistant-widget`
- `packages/assistant-widget`
- `apps/assistant-demo`
- `.changeset/config.json`
- `changesets/action`
- `assistant-widget-v<version>`

### Expected change surface

- Separate reusable package from demo application.
- Configure Changesets.
- Replace the existing tag-driven publishing workflow with the standard Changesets release workflow.
- Preserve npm Trusted Publishing.
- Update documentation.

### Excluded areas

- Widget UI behaviour
- Backend
- Admin application
- RAG UI
- Custom release tooling
- `semantic-release`
- `release-it`
- Conventional Commits
- Automatic semantic version inference
- Publishing unrelated workspaces

### Unknowns Codex must verify

- Current recommended Changesets configuration for npm workspaces.
- Whether the repository should use a dedicated release branch or the standard release PR model.
- Existing npm Trusted Publishing configuration.
- Required workflow permissions.
- Any package paths that require updating after moving the workspace.

## Objective

Convert the assistant into a clearly separated reusable package and adopt the standard Changesets
release workflow.

The reusable widget must live in:

`packages/assistant-widget`

The runnable demo must live in:

`apps/assistant-demo`

The widget package must continue to be published as:

`@redmoor/assistant-widget`

The repository must use the standard Changesets release workflow:

1. Widget PR includes a Changeset.
2. Widget PR merges to `main`.
3. Changesets updates or creates the Release PR.
4. Release PR is reviewed and merged.
5. Package is published automatically.
6. Release tag is created automatically.

Do not implement a custom release pipeline where standard Changesets functionality already exists.

## Current architecture

The reusable widget currently lives inside `apps/assistant`. This workspace contains both:

- Reusable package
- Local development/demo application

The package is already configured as `@redmoor/assistant-widget` and exposes a stable public package
API.

The current publishing workflow relies on manually updating the package version and manually
creating release tags.

## Required implementation

### 1. Package separation

Move the reusable widget into `packages/assistant-widget`.

Move the runnable demo into `apps/assistant-demo`.

The demo must consume the widget through its public package API. It must not import implementation
files directly.

### 2. Preserve public API

Preserve:

- Package name
- Exports
- Stylesheet export
- TypeScript declarations
- Public types
- Peer dependencies
- Package verification
- Consumer fixture
- Deep-import protection

Existing consumers must not require code changes.

### 3. Workspace configuration

Update npm workspaces to include packages. Prefer:

```json
{
  "workspaces": [
    "apps/*",
    "packages/*"
  ]
}
```

unless repository conventions require another equivalent structure.

### 4. Configure Changesets

Install `@changesets/cli`.

Create `.changeset/config.json` and configure Changesets using the recommended workspace
configuration.

Do not create custom versioning infrastructure.

### 5. Standard release workflow

Adopt the standard Changesets workflow.

Widget changes that affect the published package must include a Changeset. Typical example:

```md
---
"@redmoor/assistant-widget": patch
---
Improve assistant widget behaviour.
```

Changesets owns:

- Release intent
- Semantic version calculation
- Version updates
- Changelog generation
- Publication

Do not replace this behaviour with custom scripts.

### 6. GitHub Actions

Replace the current release workflow with the standard `changesets/action`.

The workflow should:

- Install dependencies
- Restore cache where appropriate
- Run lint
- Run tests
- Build the package
- Run package verification
- Execute `changesets/action`

When pending Changesets exist:

- Create or update the Release PR

When the Release PR has been merged:

- Publish the package automatically
- Create the release tag

Prefer the official documented Changesets workflow over repository-specific scripting.

### 7. Trusted Publishing

Continue using npm Trusted Publishing with GitHub OIDC.

Do not introduce long-lived npm tokens.

Continue publishing with provenance.

### 8. Manual trigger

Add `workflow_dispatch`.

The manual trigger must execute the same Changesets workflow. It must not implement an alternative
publishing mechanism.

Running the workflow manually should either update/create the Release PR or publish from the merged
Release PR state, depending on the standard Changesets action behaviour.

### 9. Package quality gates

The package must not publish unless all package verification succeeds. Run:

- Lint
- Tests
- Build
- Pack verification

before publication.

### 10. Documentation

Update:

- Repository map
- Package README
- Release documentation

Remove documentation describing:

- Manual package version updates
- Manual release tags

Document the new release flow.

## Acceptance criteria

- [ ] The reusable widget lives under `packages/assistant-widget`.
- [ ] The runnable demo lives under `apps/assistant-demo`.
- [ ] Existing public package imports continue to work.
- [ ] React remains a peer dependency.
- [ ] Changesets is configured.
- [ ] `.changeset/config.json` exists.
- [ ] Widget package changes require a Changeset.
- [ ] The repository uses the standard Changesets Release PR workflow.
- [ ] `changesets/action` creates or updates the Release PR.
- [ ] Merging the Release PR automatically publishes the widget.
- [ ] npm Trusted Publishing continues to be used.
- [ ] npm provenance remains enabled.
- [ ] No custom semantic-version logic exists.
- [ ] No custom release orchestration replaces Changesets.
- [ ] Package verification runs before publication.
- [ ] Release tags are created automatically after successful publication.
- [ ] Documentation reflects the new workflow.
- [ ] Existing consumers remain compatible.

## Tests to add or update

- Update package tests for the new workspace location.
- Update consumer fixture paths.
- Verify package exports.
- Verify deep imports remain unsupported.
- Verify package tarball contents.
- Verify the demo consumes only the published package API.
- Validate the GitHub Actions workflow using existing repository tooling.
- Do not duplicate Changesets functionality in unit tests.

## Verification commands

```sh
npm ci
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
npx changeset status
```
