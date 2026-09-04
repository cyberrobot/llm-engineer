# Task title

## Repository state

Expected branch:

Base branch:

Worktree:

Dependencies:

### Read first

- `AGENTS.md`
- nearest scoped `AGENTS.md` for the primary change area, when one exists
- `docs/architecture/repository-map.md` when ownership or cross-application context is relevant
- `docs/architecture/dependency-rules.md` when dependency or architectural boundaries are affected

### Primary change area

### Canonical implementation examples

### Relevant symbols

### Expected change surface

### Excluded areas

### Unknowns Codex must verify

---

## Objective

Describe the exact result required.

## Current architecture

Summarise only the architecture relevant to this task.

## Required implementation

Describe the required behaviour precisely.

For material UI changes:

- Prefer automated browser-based visual verification over manual Codex visual inspection.
- Use Playwright visual regression screenshots for routes, components, or states whose rendered appearance is part of the requirement.
- Combine screenshot assertions with functional assertions so visual tests do not become the sole proof of correct behaviour.
- Cover relevant loading, empty, error, success, authorization, and responsive states where applicable.
- Keep visual tests deterministic by controlling data, viewport, animations, fonts, asynchronous loading, and time-dependent content where necessary.
- Manual visual review may supplement automated tests for genuinely new or substantially redesigned interfaces, but it must not be the primary acceptance criterion.

## Acceptance criteria

- [ ] Add measurable acceptance criteria.
- [ ] Include expected API or UI behaviour.
- [ ] Include failure and edge-case behaviour.
- [ ] For material UI changes, add or update automated browser coverage for the affected page or state.
- [ ] For material UI changes where visible output is part of the requirement, add or update visual regression coverage.
- [ ] Do not rely on manual Codex visual verification as the primary evidence that UI behaviour or rendering is correct.

## Tests to add or update

- Add the expected test locations.
- Describe important cases.
- For material UI changes, add or update Playwright browser tests for the affected routes, interactions, and states.
- Add or update Playwright visual regression snapshots when layout, styling, typography, spacing, responsive behaviour, or other rendered output is materially changed.
- Use functional assertions for behaviour and screenshot assertions for visual regression.
- Ensure visual tests are deterministic and suitable for CI.
- Avoid requiring manual Codex visual testing when the result can be verified automatically.

## Verification commands

```bash
# Add the exact commands Codex must run.
# For material UI changes, include the relevant browser and visual regression test commands.
```
