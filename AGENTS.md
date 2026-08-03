# Shared Engineering Rules

## Core Principles

- Inspect and understand the repository before changing it.
- Prefer the smallest complete, backward-compatible change that satisfies the requirement.
- Reuse proven libraries and existing project abstractions before creating new ones.
- Keep each change independently reviewable, testable, deliverable, and limited to its stated scope.
- Verify externally observable behaviour and business rules, not implementation details or coverage numbers.
- Never claim a command or scenario passed unless it was actually run successfully.

## Repository Inspection and Scope

Before implementation:

1. Inspect the relevant domain models, services, repositories, factories, utilities, configuration, dependencies, conventions, and tests.
2. Identify expected behaviour, invariants, failure modes, security boundaries, callers, stored data, and public contracts.
3. Confirm prerequisite branches or earlier pull requests are present. If repository state contradicts task assumptions, stop and report the mismatch instead of recreating missing work.
4. Follow existing structure and naming unless a documented reason justifies a change.

Assume each pull request begins on a fresh feature branch. Implement only its owned scope and make dependencies on earlier work explicit. Avoid unrelated refactoring, renaming, formatting, dependency upgrades, migrations, or architecture changes. In parallel worktrees, minimise overlap in shared bootstrap, exports, migrations, and dependency-injection files.

## Design and Reuse

### Reuse order

Prefer, in order:

1. The standard library.
2. Existing project libraries and utilities.
3. Existing services, repositories, factories, ports, adapters, serializers, validators, configuration, logging, clocks, ID generators, filesystem helpers, and dependency-injection wiring.
4. When the existing stack is unsuitable, either a small local implementation for simple, non-specialised behaviour or a mature, maintained, licence-compatible library for specialised capability.

Do not introduce parallel implementations or multiple libraries for the same capability. A new dependency must provide a clear benefit, avoid duplicating the existing stack, and be documented.

### Composition and boundaries

Compose or extend stable components before adding a framework, base class, service layer, or generic abstraction. Add an abstraction only for multiple concrete uses with a clear shared contract and a net reduction in complexity.

Keep responsibilities separated:

- Domain code owns business rules and must not depend on transport, CLI parsing, database sessions, application startup, dependency-injection containers, or provider clients.
- Orchestration coordinates components without reimplementing their rules.
- Persistence stores and retrieves data without making business decisions.
- Presentation formats outcomes without calculating them.
- Integration adapters contain provider-specific types and map them to application-owned models.
- Lower-level modules must not import higher-level entry points. Avoid circular imports and startup-dependent package exports.

Keep functions and classes focused. Extract shared code when it represents the same rule, not merely similar syntax. Prefer explicit code and business-oriented names over clever or speculative abstractions. Comments should explain constraints and non-obvious decisions, not restate code. Remove dead code, temporary debugging, commented-out implementations, and unused compatibility layers.

## Public Contracts and Compatibility

Treat existing public behaviour as a contract, including APIs, exports, serialized data, persisted formats, schemas, configuration and environment keys, CLI arguments and exit codes, events, integrations, and user workflows.

- Prefer additive fields, compatible defaults, optional features, adapters, and deprecation periods. Omitted options must retain existing behaviour.
- Keep exports deliberate and minimal; do not expose private helpers.
- Before changing a contract, identify consumers and stored data, add contract coverage, define a migration path, and make transition state observable.
- If compatibility cannot be preserved, document the reason, affected consumers, migration and rollout steps, rollback strategy, and removal criteria before implementation.
- For substantial changes, establish a tested baseline, separate mechanical refactoring from behavioural changes, migrate incrementally, keep each step deployable and reversible, and remove legacy code only after consumers have moved.
- A rewrite requires explicit scope, approval, parity criteria, migration tests, rollout safeguards, and evidence that incremental change is riskier or costlier.

## Testing

### Test observable behaviour

Tests must fail for realistic defects and verify results through public interfaces: endpoints, exported functions, public service methods, rendered interactions, persisted state, files, and observable side effects. Refactoring internals without changing behaviour should not break tests.

Do not test private helpers, internal variables or structure, exact internal call order, or a mock call without verifying its outcome. Never write tests merely to increase coverage or endorse the current implementation.

### Development process

For every feature or bug fix, where practical:

1. Add or update behaviour-focused tests before production code.
2. Run the new test and confirm it fails for the expected reason.
3. Implement the smallest production change.
4. Run targeted tests, the broader affected suite, integration checks, type checking, formatting, and linting using repository commands.
5. Review whether the suite catches plausible mutations such as removed validation or ownership filters, reversed comparisons, skipped transactions, duplicate creation, omitted constraints, hard-coded results, ignored provider failure, unintended field resets, and invalid state transitions.

Every bug fix needs a clearly named regression test that reproduces the defect and fails before the fix, unless automated testing is genuinely impossible and the reason is documented. Never weaken expected behaviour or assertions to accommodate an implementation.

### Assertions

Use precise assertions for status or result type, response fields, persisted values, ownership, counts, transitions, timestamps, immutable fields, events, side effects, and user-visible output. Avoid truthiness-only checks, “no exception” checks, mock-call-only checks, status-only checks, or broad snapshots. Snapshots may supplement but never replace semantic assertions. Avoid brittle complete exception-string or log assertions when structured data is available.

### Prohibited test practices

Never:

- Delete a test solely because a change breaks it.
- Skip or disable a failure without a documented valid reason, or commit focused tests such as `.only`.
- Loosen a meaningful assertion, replace it with a snapshot, hide failures, or mock away the behaviour under test.
- Change production code solely for test convenience when realistic setup is possible.
- Change expected behaviour merely to match the current implementation.

If a test appears wrong, confirm intended behaviour and explain the correction.

## Verification and Documentation

Run the repository-defined commands relevant to the change:

- Targeted and broader affected tests, plus integration or end-to-end suites where applicable.
- Type checking, linting, and formatting checks.
- Database migrations and persistence checks when storage changes.
- Manual verification of changed public entry points where practical.

If a command cannot run, report the exact command, reason, observed error, and remaining risk. Do not declare completion while relevant checks fail.

Update documentation for public APIs, configuration, operations, persisted formats, exit codes, side effects, failure and retry behaviour, idempotency, compatibility, recovery, and migration procedures. Keep examples accurate, never describe planned behaviour as implemented, and record justified deviations.

## Completion Report

For implementation work, report:

1. Branch and files changed.
2. Behaviour and tests added or updated, including the initial expected failure where practical.
3. Production changes and important design or reuse decisions.
4. Migrations, configuration, dependencies, and public-interface changes.
5. Commands actually run and their final results.
6. Known limitations, unverified behaviour, repository mismatches, deviations, and remaining risks.

Completion requires defined behaviour, meaningful regression coverage, passing relevant tests, type checks, and linting, verified security and persistence boundaries where applicable, and explicit disclosure of remaining limitations.

## GitHub Branches and Pull Requests

Create a new branch only after fetching the latest remote state. Base it on current `origin/main` with `git switch --no-track -c <branch> origin/main`; never use a stale local branch or configure a feature branch to track the default branch. On first push, use `git push --set-upstream origin <branch>` and verify it tracks the same-named remote branch.

Sandboxed `gh auth status` may not see host keychain credentials. Before requesting login, run `gh auth status` and `gh repo view --json nameWithOwner,defaultBranchRef` with the necessary host permission. Ask for `gh auth login` only if those checks fail outside the sandbox.

When commit, push, and pull-request creation are requested:

1. Inspect `git status -sb` and the diff.
2. Stage only in-scope files; leave unrelated work untouched unless the user confirms inclusion.
3. Commit with a concise description of the complete change.
4. Push the feature branch to the same-named remote branch with upstream tracking; never push it to the default branch.
5. Open a draft pull request against the repository default branch unless the user requests another base or ready-for-review status.
6. Use a Markdown body with real newlines describing the change, impact, and checks that actually passed.
7. Verify and report branch, commit, base, URL, draft status, and deliberately uncommitted files.
