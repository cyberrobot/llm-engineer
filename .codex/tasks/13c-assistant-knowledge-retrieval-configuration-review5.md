# PR 13C — Final Review Fixes (Follow-up)

Continue work on the existing branch:

`feature/13c-assistant-knowledge-retrieval-configuration`

Do **not** create a new PR.

---

## Objective

Address the remaining review findings from PR #66.

These are intentionally small follow-up fixes.

Do not introduce new features or refactor unrelated code.

---

# Issue 1 — Clear unknown-operation state after a definitive create failure

The current implementation correctly preserves unknown-outcome create operations after network/server failures.

However, after the user retries the **identical request** and receives a **definitive backend response** (for example validation failure or idempotency conflict), the UI incorrectly continues treating the operation as "unknown".

Current behaviour leaves:

- `unknownOutcome === true`
- retained unknown-operation UI
- new creation disabled
- identical retry removed
- authoritative refresh incorrectly required for every subsequent operation

This is incorrect because the server has now produced an authoritative result.

## Required behaviour

After any definitive create response:

- clear the retained unknown-operation state
- clear the retained operation identity where appropriate
- stop rendering unknown-outcome messaging
- stop disabling creation because of unknown state

The UI should now follow the semantics of the definitive error that was returned.

Examples:

Validation error

- unknown state cleared
- user edits values normally
- next submission becomes a new logical operation
- fresh idempotency key

Idempotency conflict

- unknown state cleared
- show existing refresh guidance
- follow normal conflict behaviour rather than unknown-outcome behaviour

The implementation must not continue presenting the request as unresolved once the backend has responded definitively.

---

# Issue 2 — Add regression tests

Add behaviour-focused regression coverage.

At minimum verify:

## Unknown -> validation failure

Scenario:

1. create returns network/server failure
2. identical retry
3. backend returns validation error

Verify:

- unknown-operation UI disappears
- retry button disappears
- creation is no longer blocked by unknown state
- user may edit the form normally
- next logical submission uses a fresh idempotency key

---

## Unknown -> idempotency conflict

Scenario:

1. create returns unknown outcome
2. identical retry
3. backend returns idempotency conflict

Verify:

- unknown-operation state is cleared
- UI follows conflict handling
- refresh guidance is shown
- unknown-outcome messaging is gone

---

# Documentation

Update the PR description if necessary so that:

- verification reflects the final HEAD commit
- workflow status reflects the completed CI run
- verification counts match the final implementation

No code documentation changes are required.

---

# Constraints

Do not modify:

- backend
- API contracts
- routing
- idempotency implementation
- retrieval workflow
- Storybook stories unless required by tests

Keep the change minimal.

---

# Verification

Run the focused admin tests covering create workflows.

Then run the normal admin verification suite already used by this PR.

Confirm:

- lint passes
- typecheck passes
- admin tests pass
- build passes

Do not claim manual browser verification unless actually performed.

---

# Completion report

Report:

1. Files changed.
2. Root cause.
3. Behaviour after fix.
4. Tests added.
5. Commands run.
6. Final results.
