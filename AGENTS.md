# Shared Engineering Rules

## Core Principles

- Inspect and understand the repository before changing it.
- Prefer the smallest complete, backward-compatible change that satisfies the requirement.
- Reuse proven libraries and existing project abstractions before creating new ones.
- Keep each change independently reviewable, testable, deliverable, and limited to its stated scope.
- Do not perform unrelated refactors or dependency upgrades.
- Verify externally observable behaviour and business rules, not implementation details or coverage numbers.
- Never claim a command or scenario passed unless it was actually run successfully.

## Repository Inspection and Scope

### Repository navigation

Read the task, this file, `git status -sb`, and the nearest scoped `AGENTS.md`; scoped guidance
supplements or overrides this file. Inspect the smallest implementation, configuration, test, or
existing-diff surface relevant to the task. Read a README or manifest only when it defines behaviour,
commands, dependencies, configuration, or contracts relevant to the change. Start from a concrete
symbol, route, configuration key, business concept, or filename and follow direct imports, callers,
ports, adapters, registrations, and public contracts outward only as needed. Do not scan or enumerate
the entire repository as a default discovery step.

Read `docs/architecture/repository-map.md` when ownership is unclear, work is cross-application, a
significant boundary is introduced or relocated, or focused inspection cannot identify ownership.
Read `docs/architecture/dependency-rules.md` when changing dependencies between layers, packages, or
apps; moving responsibilities; adding shared abstractions or infrastructure; changing ports/adapters;
or making architecture-sensitive refactors.

Current scoped guidance:

- `apps/backend/AGENTS.md` applies to backend code, tests, migrations, operations, and backend docs.
- `apps/admin/AGENTS.md` applies to the Admin application.
- `packages/assistant-widget/AGENTS.md` applies to the published assistant widget, package fixtures,
  and tests.
- `apps/rag-ui/` currently has no scoped file, so this root file remains authoritative there.

For every task:

1. Search within the selected subtree; prefer scoped `rg` commands over repository-wide searches.
2. Expand into another subtree only when a dependency trail or public contract requires it.
3. Inspect bootstrap, exports, migrations, dependency injection, and lockfiles only when the change
   crosses those boundaries. Exclude generated and runtime directories from discovery.

For backend work, start in the owning context; for frontend work, start in the affected component or
feature and its API boundary; for documentation, start with the named document and the command or
implementation it describes. Repository-wide enumeration is a last resort: state the uncertainty and
filter generated and ignored content. Before implementation, identify the relevant invariants,
failure modes, security boundaries, callers, stored data, and public contracts. If repository state
contradicts task prerequisites, report it rather than recreating missing work.

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

Test realistic observable behaviour through endpoints, public APIs, rendered interactions, persisted
state, files, and side effects. Use precise assertions, not implementation details, mock-call-only
checks, broad snapshots, or truthiness. Add regression coverage for defects where practical; do not
delete, weaken, skip, or mock away meaningful tests to make an implementation pass.

## Verification and Documentation

Run the repository-defined commands relevant to the change:

- Targeted and broader affected tests, plus integration or end-to-end suites where applicable.
- Type checking, linting, and formatting checks.
- Database migrations and persistence checks when storage changes.
- Manual verification of changed public entry points where practical.

If a command cannot run, report the exact command, reason, observed error, and remaining risk. Do not declare completion while relevant checks fail.

Update documentation for public APIs, configuration, operations, persisted formats, exit codes, side effects, failure and retry behaviour, idempotency, compatibility, recovery, and migration procedures. Keep examples accurate, never describe planned behaviour as implemented, and record justified deviations.

## Completion Report

Report what changed, checks actually run and their result, material public/configuration/migration
changes, and known limitations or risks. Do not claim success for an unrun check.

## Git and GitHub

When branch, commit, push, or pull-request operations are requested, follow
`docs/engineering/git-workflow.md`.
