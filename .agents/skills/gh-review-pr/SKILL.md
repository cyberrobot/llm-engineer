---
name: gh-review-pr
description: Review a GitHub pull request against its governing specification and report measurable progress. Use when the user asks for a PR review, implementation audit, spec-compliance review, completion percentage, missing requirements, or an approvability decision.
---

# GitHub PR Specification Review

Review the complete pull request against the authoritative specification and make progress visible. Prefer the GitHub app for PR metadata, patch context, and comments. Use local `git` and `gh` only for gaps such as current-branch PR discovery, checks, or thread state.

## Workflow

1. Resolve the pull request and specification.
   - Use an explicitly provided PR URL or number and spec path or URL.
   - For "this PR", resolve the current branch PR from local git context.
   - Locate repository task or specification documents linked by the PR, named by the user, or clearly associated with the branch. Do not invent requirements from the implementation.
   - If more than one document could be authoritative, state which one is used and why. Ask for clarification only when that choice would materially change the verdict.
2. Establish the review baseline.
   - Inspect the full diff against the PR base, not only the latest commit.
   - Read the repository instructions and the implementation, tests, migrations, configuration, and documentation directly implicated by the specification.
   - Inspect review threads and CI status when they affect approvability. Use the specialist GitHub comment or CI workflow when thread state or Actions logs require it.
3. Build a requirement ledger before deciding the verdict.
   - Decompose the specification into independently verifiable, externally observable requirements.
   - Keep explicit acceptance criteria as separate requirements when each can independently pass or fail.
   - Do not inflate the denominator with headings, background prose, duplicated statements, implementation suggestions, or verification commands.
   - Assign every requirement exactly one status: `complete`, `partial`, `missing`, or `not applicable`.
   - Support each status with concrete evidence from the diff, repository state, tests, CI, or documentation. Mark uncertain evidence as unverified rather than assuming completion.
4. Calculate completion consistently.
   - Exclude `not applicable` requirements from the denominator and explain each exclusion.
   - Score `complete` as 1, `partial` as 0.5, and `missing` as 0.
   - Calculate `completion percentage = 100 × earned points / applicable requirements` and round to the nearest whole percent.
   - Show the counts and formula beside the percentage so the result is auditable.
5. Decide approvability independently from the percentage.
   - Return `Yes` only when there are no blocking findings, no missing or partial must-have requirements, required checks pass, and required evidence is available.
   - Return `No` when any correctness, security, data-integrity, compatibility, migration, required-test, or explicit must-have requirement remains unresolved.
   - Return `Conditional` only when implementation requirements are complete but approval depends on a clearly identified external or pending condition, such as an in-progress required check.
   - Never use a high completion percentage to override a blocking gap.
6. Report findings before the summary.
   - List actionable findings in severity order with precise file and line references when available.
   - Tie every finding to a requirement or an approvability gate.
   - Distinguish implementation gaps from missing verification evidence.
7. End every review with the required review summary format.

## Required Review Summary

Use this structure even when there are no findings:

```markdown
## Review summary

- Spec completion: NN% (C complete + P×0.5 partial out of T applicable requirements; N not applicable)
- Incomplete requirements: <total> (<missing> missing, <partial> partial)
- Approvable: Yes | No | Conditional — <one-sentence reason>

### Missing or partial requirements

1. [Missing|Partial] <requirement> — <evidence and concrete work still needed>

### Requirement ledger

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | ... | Complete | `path:line`, test, check, or observed behavior |

### Approval blockers

- <blocking finding, failed required check, or "None">

### Verification

- Passed: <checks actually observed passing>
- Pending/failed/not run: <checks and resulting risk>
```

If nothing is incomplete, write `None` under missing or partial requirements. Keep the ledger concise but complete; group truly atomic repeated cases only when they share the same implementation and evidence.

## Review Integrity

- Treat absent evidence as unverified, not complete.
- Do not claim a test or check passed unless its successful result was observed.
- Do not modify code, submit a review, approve, comment, or resolve threads unless the user explicitly asks for that write action.
- Separate pre-existing issues outside the PR diff from PR-introduced or spec-related blockers.
- State when the specification is unavailable or too ambiguous to calculate a defensible percentage. In that case report `Spec completion: Not measurable`, list the missing source, and give an approvability verdict only from available evidence.
