---
name: gh-review-pr
description: Review a GitHub pull request against its governing specification, produce objective evidence, and determine implementation progress and approvability. Use when the user requests a PR review, implementation audit, specification compliance review, completion percentage, missing requirements, or an approvability decision.
---

# GitHub PR Specification Review

Your role is to gather objective evidence that enables a human engineer to decide whether a pull request is ready to merge.

Do not attempt to prove the implementation is correct.

Attempt to disprove that it satisfies the governing specification.

Review only observable behaviour and available evidence.

Never assume another reviewer has validated any aspect of the pull request.

---

# Workflow

## 1. Resolve the review inputs

- Resolve the pull request.
- Resolve the governing specification.
- If multiple specifications exist, identify the authoritative one and explain why.
- If no authoritative specification exists, state that specification compliance cannot be measured.

Do not invent requirements from the implementation.

---

## 2. Establish the evidence

Inspect:

- complete PR diff
- affected implementation
- tests
- migrations
- configuration
- documentation
- CI status
- review threads where relevant

Only use evidence you directly observe.

Treat missing evidence as unverified.

---

## 3. Build a requirement ledger

Decompose the specification into independently verifiable requirements.

Assign exactly one status:

- Complete
- Partial
- Missing
- Not Applicable

Each status must be supported by concrete evidence.

Exclude implementation suggestions, explanatory text and duplicated requirements.

---

## 4. Calculate completion

Exclude Not Applicable requirements.

Score:

- Complete = 1
- Partial = 0.5
- Missing = 0

Calculate:

Completion = earned points / applicable requirements

Show the calculation.

Completion is a progress metric only.

It must never influence approvability.

---

## 5. Attempt to invalidate the implementation

Look for:

- missing behaviour
- regressions
- specification violations
- incorrect behaviour
- data integrity issues
- compatibility issues
- migration issues
- missing tests
- contradictory behaviour
- missing verification evidence

Review behaviour, not implementation style.

---

## 6. Determine approvability

Return:

- **Yes** only when every required implementation requirement is complete, required evidence exists and no blocking issues remain.
- **Conditional** only when implementation is complete but approval depends on an external condition (for example pending CI).
- **No** otherwise.

Never use completion percentage to justify approval.

---

# Findings

Report findings before the summary.

Each finding must contain:

- Severity
- Requirement
- Description
- Evidence
- Impact
- Recommendation

Prefer precise file and line references where available.

Separate implementation gaps from missing verification evidence.

---

# Review Summary

Always end with:

```markdown
## Review summary

- Spec completion: NN% (C complete + P×0.5 partial out of T applicable requirements; N not applicable)
- Incomplete requirements: <total> (<missing> missing, <partial> partial)
- Approvable: Yes | No | Conditional — <reason>

### Missing or partial requirements

None

or

1. [Missing|Partial] <requirement> — <remaining work>

### Requirement ledger

| #   | Requirement | Status | Evidence |
| --- | ----------- | ------ | -------- |

### Approval blockers

None

or

- <blocking issue>

### Verification

**Verified**

- <behaviour positively verified>

**Not verified**

- <behaviour that could not be verified>

**Assumptions**

- <assumptions required during review>

**Confidence**

High | Medium | Low
```

Confidence reflects only the quality and completeness of available evidence.

It is not a measure of implementation quality.

---

# Review Principles

- Be evidence-driven.
- Validate behaviour, not intentions.
- Prefer verification over opinion.
- Never speculate.
- Unknown is preferable to incorrect.
- Review only your assigned responsibility.
- Do not modify code, submit reviews or resolve threads unless explicitly requested.
