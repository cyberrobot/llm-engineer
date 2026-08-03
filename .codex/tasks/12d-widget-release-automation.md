# PR 12D — Widget Release Automation

## Repository state

Expected branch: feature/12d-widget-release-automation

Base branch: main

Worktree: Frontend

Dependencies: PR 12C — Versioned Widget Library must be merged first.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `apps/assistant/package.json`
- `apps/assistant/README.md`

### Primary change area

- `.github/workflows/`
- `apps/assistant/package.json`
- Widget release documentation only where required

### Canonical implementation examples

- Existing repository GitHub Actions conventions
- Existing `apps/assistant` scripts: `build`, `pack:check`, and `pack:verify`

### Relevant symbols

- npm package: `@redmoor/assistant-widget`
- package workspace: `apps/assistant`

### Expected change surface

- Add a GitHub Actions workflow that verifies and publishes the widget package.
- Add only the package metadata or scripts required by that workflow.

### Excluded areas

- Widget UI or runtime behaviour
- Backend changes
- Automatic semantic-version calculation
- Changelog generation
- GitHub Release creation
- Publishing other workspaces

### Unknowns Codex must verify

- Existing workflow naming, Node version, npm registry configuration, and lockfile commands
- Whether npm trusted publishing is configured; prefer OIDC trusted publishing and document any required repository/npm setup
- Whether scoped publication requires `--access public`

---

## Objective

Provide a safe, explicit release workflow that publishes the already-versioned `@redmoor/assistant-widget` package to npm after validating that the selected Git tag matches the package version.

## Current architecture

The widget is an npm workspace in `apps/assistant`. PR 12C makes it publishable and provides build and package-verification scripts. The repository does not yet automate publication.

## Required implementation

Add a GitHub Actions workflow triggered by tags matching `assistant-widget-v*` and by manual dispatch.

The workflow must:

1. Check out the exact release ref and install dependencies using the repository lockfile.
2. Use the repository-supported Node version and npm registry configuration.
3. Read `apps/assistant/package.json` and require the release tag to equal `assistant-widget-v<package-version>`.
4. Fail before publication when the tag/version is malformed or mismatched.
5. Run the widget lint, test, build, and package-verification commands.
6. Publish only the `apps/assistant` workspace to npm, with provenance and public access where required.
7. Use GitHub environment protection or equivalent workflow permissions so publishing cannot occur from pull-request workflows.
8. Document the one-time npm/GitHub configuration and the exact release procedure.

Keep version changes manual and reviewable in `apps/assistant/package.json`. Do not create custom release tooling where standard npm and GitHub Actions behaviour is sufficient.

## Acceptance criteria

- [ ] Pushing `assistant-widget-v0.1.0` publishes only when `apps/assistant/package.json` is version `0.1.0`.
- [ ] A mismatched or malformed tag fails before `npm publish`.
- [ ] Lint, tests, build, and package verification must pass before publishing.
- [ ] The workflow publishes only `@redmoor/assistant-widget`.
- [ ] Publication uses least-privilege permissions and npm provenance.
- [ ] Re-running a release for an already-published version fails safely without changing repository state.
- [ ] Documentation explains version bumping, tag creation, required npm configuration, and failure recovery.

## Tests to add or update

- Add a small testable script only if tag/version validation cannot remain clear and reliable inside the workflow.
- Cover valid, mismatched, malformed, and prerelease versions if a script is added.
- Do not test GitHub Actions by duplicating the workflow logic in application tests.

## Verification commands

```bash
npm ci
npm run lint --workspace @redmoor/assistant-widget
npm run test --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

# Validate workflow syntax using the repository's existing workflow linter,
# or actionlint if already available.
```
