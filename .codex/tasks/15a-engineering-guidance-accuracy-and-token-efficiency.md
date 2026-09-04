# 15a — Engineering Guidance Accuracy and Token Efficiency

## Repository state

Expected branch:

`15a-engineering-guidance-token-efficiency`

Base branch:

`main`

Worktree:

Fresh worktree or feature branch from current `origin/main`.

Dependencies:

None. This PR updates engineering guidance only and must not depend on application feature work.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `.codex/tasks/TEMPLATE.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `apps/backend/README.md`
- `apps/backend/pyproject.toml`
- `apps/backend/package.json`
- `apps/admin/package.json`
- `packages/assistant-widget/AGENTS.md`

Do not recursively inspect the repository. Read only enough current implementation structure to verify that the guidance being documented is accurate.

### Primary change area

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `apps/admin/AGENTS.md` — new
- `.codex/tasks/TEMPLATE.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `docs/engineering/backend-testing.md` — new
- `docs/engineering/git-workflow.md` — new

### Canonical implementation examples

Use the current bounded-context architecture as the source of truth:

- `apps/backend/assistant/domain/`
- `apps/backend/assistant/application/`
- `apps/backend/assistant/application/ports/`
- `apps/backend/assistant/infrastructure/`
- `apps/backend/admin_auth/`
- `apps/backend/operations/`
- `apps/backend/core/`
- `apps/backend/infrastructure/`
- `apps/backend/shared/`

For the current RAG persistence boundary, inspect:

- `apps/backend/assistant/application/ports/rag_knowledge_repository.py`
- `apps/backend/assistant/infrastructure/repositories/rag_knowledge.py`
- `apps/backend/assistant/application/rag_chat.py`
- `apps/backend/docs/rag-persistence-contract.md`

For Admin application structure, inspect:

- `apps/admin/src/App.tsx`
- `apps/admin/src/routing.ts`
- `apps/admin/src/api/`
- `apps/admin/src/auth/`
- `apps/admin/src/components/`
- `apps/admin/src/features/`
- `apps/admin/package.json`

Use `packages/assistant-widget/AGENTS.md` as an example of application/package-specific scoped guidance.

### Relevant symbols and concepts

- root versus scoped `AGENTS.md`
- repository ownership
- dependency direction
- application-owned ports
- infrastructure adapters
- composition root
- behaviour-focused testing
- public contracts
- compatibility
- authorization boundaries
- verification commands
- conditional documentation loading
- Codex context/token efficiency

### Expected change surface

Expected:

- engineering guidance
- architecture documentation
- Codex task template
- new scoped Admin guidance
- extracted conditional testing and Git workflow documentation

Not expected:

- application implementation
- backend runtime behaviour
- API contracts
- database schemas or migrations
- frontend behaviour
- CI workflow behaviour
- dependencies or lockfiles

### Excluded areas

Do not:

- refactor production code to match documentation;
- rename backend packages or bounded contexts;
- change API behaviour;
- change authentication or authorization behaviour;
- modify database migrations;
- alter CI workflows;
- introduce a documentation framework;
- add generated documentation;
- pin or upgrade Python/JavaScript dependencies;
- change `requirements.txt` solely as part of this guidance cleanup;
- rewrite existing historical `.codex/tasks/*.md` specifications;
- change Playwright or visual-regression requirements already present in `.codex/tasks/TEMPLATE.md`, except where necessary to fit the revised conditional-read structure.

### Unknowns Codex must verify

Before editing:

1. Verify every path currently named by `repository-map.md` and `dependency-rules.md`.
2. Verify whether any additional scoped `AGENTS.md` files have been introduced since this specification was written.
3. Verify current Admin package commands from `apps/admin/package.json`.
4. Verify current backend commands from `apps/backend/README.md`, `apps/backend/package.json`, and `apps/backend/pyproject.toml`.
5. Verify the current RAG application port and PostgreSQL repository paths.
6. Search for references to obsolete `apps/backend/app/...` architecture paths in current engineering documentation.
7. Verify that any guidance moved out of an `AGENTS.md` remains discoverable from an appropriate conditional reference.

If current repository state contradicts this specification, preserve the current implemented architecture and update the documentation accordingly rather than restoring an obsolete structure.

---

## Objective

Make the repository's AI/Codex engineering guidance accurate for the current architecture while materially reducing the amount of guidance that must be loaded for every task.

The result must preserve the existing engineering quality bar while separating:

- rules that apply to almost every task;
- application-specific rules;
- architecture information needed only for boundary-changing work;
- detailed testing guidance needed only for relevant backend work;
- Git/GitHub procedures needed only when Git operations are requested.

The guidance should direct Codex toward the smallest relevant context rather than requiring several large documentation files before every change.

---

## Current architecture

The repository currently has a root `AGENTS.md` containing repository navigation, engineering principles, compatibility, testing, verification, completion reporting, and detailed Git/GitHub workflow instructions.

`apps/backend/AGENTS.md` contains backend-specific guidance for:

- domain modelling;
- validation;
- determinism;
- idempotency;
- concurrency;
- persistence;
- files;
- external services;
- errors;
- retries;
- security;
- observability;
- testing.

Both documents currently require `docs/architecture/repository-map.md` and `docs/architecture/dependency-rules.md` to be read before backend implementation.

`.codex/tasks/TEMPLATE.md` independently lists the same architecture documents under `Read first`, causing the same large static documents to be loaded for tasks even when their architecture is already precisely scoped by the task specification.

`docs/architecture/repository-map.md` reflects most of the current backend bounded-context structure but does not give the now-established `apps/admin` application equivalent first-class navigation guidance.

`docs/architecture/dependency-rules.md` contains stale paths from an earlier backend architecture, including `apps/backend/app/...`, and its high-level dependency representation risks implying that Domain depends on Persistence.

The current implementation instead uses:

```text
API
 ↓
Application
 ↓
Domain

Application
 ↓
application-owned ports

Infrastructure
 ├─ implements application-owned ports
 └─ may map persistence/provider representations to application/domain models
```

The composition/bootstrap layer may know concrete implementations in order to wire the system. Lower-level domain and application code must not import composition entry points.

The current RAG implementation follows that structure through an application-owned `RagKnowledgeRepository` port with a PostgreSQL implementation under Assistant infrastructure.

---

## Required implementation

### 1. Correct `docs/architecture/dependency-rules.md`

Rewrite the stale backend dependency guidance to describe the architecture that actually exists.

Remove obsolete references to:

```text
apps/backend/app/services/retrieval/
apps/backend/app/infrastructure/embeddings/
apps/backend/app/persistence/vector/
```

Do not replace them with another speculative directory hierarchy.

Document the current architectural roles instead.

The dependency model must make clear that:

- API depends on application services and transport-facing domain/application models where appropriate.
- Application services depend on domain rules and application-owned ports.
- Domain code remains independent of FastAPI, databases, Redis, OpenAI, provider clients, environment configuration, and application startup.
- Infrastructure implements application-owned ports and may depend inward on application contracts and domain models.
- Persistence adapters belong to infrastructure; persistence is not a dependency of Domain.
- Composition/bootstrap code may know concrete implementations in order to construct the application.
- Lower-level modules must not import application startup or composition roots.
- Concrete infrastructure adapters must not become the normal dependency surface of application services when a port exists.

Update the AI/RAG section to reference current ownership patterns rather than obsolete paths.

Use the existing RAG repository implementation as a concrete example where useful:

```text
assistant/application/ports/
        ↑
assistant/infrastructure/
```

Keep the document short enough to function as an architectural constraint reference rather than a second repository map.

---

### 2. Update `docs/architecture/repository-map.md`

Bring the repository map in line with the current application structure.

Add a first-class `apps/admin` section covering at minimum:

- `src/App.tsx`
- `src/routing.ts`
- `src/api/`
- `src/auth/`
- `src/components/`
- `src/features/`
- relevant tests
- configuration
- Storybook/configuration locations where currently present
- `package.json`

Describe the intended navigation direction for an Admin change:

```text
affected feature/page
→ shared components when required
→ API/auth boundary when required
→ App/routing only when composition changes
```

State that:

- components must use established API/client boundaries rather than bypassing them;
- backend authentication/authorization remains authoritative;
- user-visible behaviour should be tested through rendered interactions;
- shared application/bootstrap files should only be inspected when the change crosses those boundaries.

Update the verification section with current Admin commands from `apps/admin/package.json`.

Verify all existing backend, RAG UI, Assistant Demo, and Assistant Widget descriptions while editing and correct any clearly stale paths encountered within this document.

Do not turn `repository-map.md` into a general engineering-rules document.

---

### 3. Reduce mandatory architecture reads in root `AGENTS.md`

Change the root navigation policy so architecture documents are loaded when they are useful rather than on every task.

The default task path should be:

1. Read the task.
2. Read root `AGENTS.md`.
3. Read the nearest scoped `AGENTS.md` for the affected subtree.
4. Inspect the smallest relevant implementation/configuration/test surface.
5. Expand outward only through concrete dependency or public-contract evidence.

`repository-map.md` should be required when:

- the owning application or layer is unclear;
- the task is genuinely cross-application;
- the task introduces or relocates a significant repository boundary;
- focused inspection cannot identify ownership.

`dependency-rules.md` should be required when:

- adding or changing a dependency between layers/packages/apps;
- moving responsibilities between layers;
- adding shared abstractions or infrastructure;
- changing application ports/adapters;
- performing architecture-sensitive refactoring.

Do not require either document for a narrowly scoped change whose owning location and dependency direction are already established.

Preserve the rule that the nearest scoped `AGENTS.md` supplements or overrides broader guidance for its subtree.

---

### 4. Add `apps/admin/AGENTS.md`

Create concise scoped guidance for the Admin application.

It must cover at minimum:

#### Navigation

Start from the narrowest affected boundary:

- feature/page under `src/features/`;
- reusable UI under `src/components/`;
- backend communication under `src/api/`;
- administrator-session behaviour under `src/auth/`;
- routing or application composition only when those boundaries actually change.

Avoid reading the whole application by default.

#### Architecture

Preserve:

```text
UI / feature
    ↓
API/auth client boundary
    ↓
backend HTTP contract
```

Admin browser code must not:

- import backend implementation modules;
- reproduce server-side authorization;
- access persistence directly;
- bypass established API clients;
- introduce a second source of truth for backend business rules.

#### React/TypeScript

Require:

- current project TypeScript conventions;
- existing React patterns;
- accessible semantic UI;
- deliberate state ownership;
- existing routing abstractions;
- existing components before creating duplicates;
- no speculative generic component abstractions.

#### Styling

Use the established Admin styling/Tailwind setup.

Do not introduce another styling framework or parallel design system.

#### Testing

Prefer rendered behaviour and user interaction through the existing test stack.

Tests should verify outcomes rather than component internals.

Browser/visual tests should follow repository infrastructure and the task specification where material rendered behaviour changes.

#### Verification

Include the current canonical Admin commands directly, using the actual workspace scripts.

At minimum verify the existence/current form of:

```bash
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
```

Only include commands that currently exist.

Keep this file application-specific. Do not copy large generic sections from root `AGENTS.md`.

---

### 5. Simplify `apps/backend/AGENTS.md`

Preserve the backend engineering quality bar while reducing always-loaded detail.

Keep concise rules for:

- bounded-context navigation;
- domain independence;
- application-owned ports;
- validation;
- determinism;
- idempotency;
- transactions;
- persistence integrity;
- provider adapters;
- configuration;
- timeouts;
- resource management;
- authorization;
- safe errors;
- retries;
- observability;
- relevant testing;
- verification.

Change its opening so `repository-map.md` and `dependency-rules.md` are conditional according to the root policy rather than mandatory on every backend task.

Do not duplicate root-level compatibility, general testing philosophy, completion reporting, or Git workflow prose unless there is a backend-specific reason.

---

### 6. Put canonical backend verification commands directly in `apps/backend/AGENTS.md`

Codex should not need to inspect the backend README merely to discover the normal quality checks.

Add a concise verification section based on the current backend configuration.

The canonical complete backend checks should include the current equivalents of:

```bash
cd apps/backend
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```

State that Codex should:

1. run the narrowest affected tests first;
2. run the broader relevant suite before completion;
3. run the complete backend checks when the change warrants full backend verification;
4. report commands that could not run rather than claiming success.

Do not duplicate detailed installation instructions from the README.

---

### 7. Extract the detailed backend test matrix

Create:

```text
docs/engineering/backend-testing.md
```

Move or consolidate detailed backend testing guidance that does not need to occupy every backend prompt, including relevant cases such as:

- malformed input;
- authentication and authorization boundaries;
- ownership and role isolation;
- boundary values;
- duplicates and retries;
- idempotency;
- concurrency;
- stale writes;
- provider failures;
- database failures;
- timeouts;
- cancellation;
- partial completion;
- rollback;
- persistence reload;
- cleanup;
- security-sensitive storage and upload behaviour.

Preserve the current standard; do not weaken it.

`apps/backend/AGENTS.md` should summarize the policy approximately as:

> Test observable behaviour through public boundaries. Cover the happy path and the boundary, authorization, persistence, idempotency/concurrency, and failure cases relevant to the changed contract. Use `docs/engineering/backend-testing.md` when the task is security-, persistence-, ingestion-, concurrency-, provider-, or failure-mode-heavy.

Do not require the detailed test document for simple backend changes where the additional matrix is irrelevant.

---

### 8. Extract Git/GitHub operating procedure

Create:

```text
docs/engineering/git-workflow.md
```

Move detailed procedural guidance that is relevant only when branch, commit, push, or PR operations are requested, including:

- basing a branch on current remote state;
- feature-branch tracking;
- staging only in-scope files;
- commit behaviour;
- push/upstream behaviour;
- draft pull-request creation;
- GitHub authentication troubleshooting;
- reporting branch/commit/PR state.

Root `AGENTS.md` should retain a concise rule such as:

> When branch, commit, push, or pull-request operations are requested, follow `docs/engineering/git-workflow.md`.

Normal implementation tasks that do not perform Git operations should not be required to load this procedural document.

Do not weaken protections against pushing unrelated changes or incorrectly reporting Git/PR state.

---

### 9. Reduce duplicate completion-report guidance

Simplify the root completion requirements.

The default completion report should require only:

- what changed;
- relevant tests/checks actually run and their result;
- important public/configuration/migration changes where applicable;
- known limitations, unverified behaviour, or remaining risks.

Do not require empty boilerplate sections for migrations, configuration, dependencies, or public interfaces when none changed.

Preserve the rule that Codex must never claim a check passed unless it actually ran successfully.

---

### 10. Keep core engineering invariants in root `AGENTS.md`

Token reduction must not remove the repository's essential engineering standards.

Root guidance must continue to require:

- repository understanding before modification;
- smallest complete change;
- backward compatibility unless explicitly changed;
- reuse before new abstractions/dependencies;
- scoped, reviewable changes;
- preservation of public contracts;
- behaviour-focused tests;
- regression coverage for defects where practical;
- no weakening/deleting tests merely to make an implementation pass;
- accurate reporting of executed checks;
- architecture boundaries;
- no speculative broad repository scans;
- no unrelated refactors or dependency upgrades.

Prefer concise, enforceable statements over long explanatory prose.

---

### 11. Update `.codex/tasks/TEMPLATE.md`

The task template must no longer defeat the token-efficiency changes by requiring the same architecture documents for every task.

Change `Read first` so it defaults to:

```text
AGENTS.md
nearest scoped AGENTS.md for the primary change area, when one exists
```

Make `repository-map.md` and `dependency-rules.md` conditional:

- include `repository-map.md` when ownership or cross-application context is relevant;
- include `dependency-rules.md` when dependency or architectural boundaries are affected.

The generated task specification itself should identify:

- primary change area;
- canonical implementation examples;
- relevant symbols;
- expected surface;
- excluded areas;
- unknowns to verify.

That task-specific context should normally replace speculative repository exploration.

Preserve the existing material-UI Playwright and visual-regression guidance.

Do not rewrite existing historical task specifications solely to adopt the new template.

---

### 12. Remove duplicated rules

After restructuring, compare:

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `apps/admin/AGENTS.md`
- `packages/assistant-widget/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `docs/engineering/backend-testing.md`
- `docs/engineering/git-workflow.md`

Remove unnecessary repetition.

Use this ownership model:

```text
Root AGENTS
    universal engineering behaviour

Scoped AGENTS
    application/package-specific behaviour

repository-map
    where code lives and where inspection starts

dependency-rules
    allowed dependency directions

backend-testing
    detailed optional backend test matrix

git-workflow
    conditional Git/GitHub procedure

task spec
    task-specific context and verification
```

A rule should normally have one authoritative home and concise references elsewhere.

---

### 13. Measure token-efficiency improvement

Use word count as a simple repository-visible proxy for always-loaded context.

Record the baseline word counts of:

```text
AGENTS.md
apps/backend/AGENTS.md
```

before modification.

After modification, compare the combined word count.

The backend default guidance path:

```text
AGENTS.md + apps/backend/AGENTS.md
```

should be at least **30% smaller** than its pre-change baseline unless preserving a specifically identified critical rule makes that target unsafe.

Do not achieve the target by deleting engineering requirements. Move conditional detail to appropriately scoped documents instead.

Report the before/after counts in the PR description or completion report.

Do not use byte count or generated token-estimation tooling as an acceptance dependency; word count is sufficient for this PR.

---

## Acceptance criteria

- [ ] `docs/architecture/dependency-rules.md` contains no obsolete `apps/backend/app/...` RAG architecture paths.
- [ ] Dependency rules no longer imply that Domain depends on Persistence.
- [ ] Application services are documented as depending on domain/application-owned contracts rather than concrete infrastructure as the normal architecture.
- [ ] The current RAG application-port/infrastructure-adapter structure is represented accurately.
- [ ] `docs/architecture/repository-map.md` contains a first-class `apps/admin` section.
- [ ] Admin navigation reflects the current `src/features`, `src/components`, `src/api`, `src/auth`, routing, and composition structure.
- [ ] Root `AGENTS.md` no longer mandates `repository-map.md` for every task.
- [ ] Root `AGENTS.md` no longer mandates `dependency-rules.md` for every task.
- [ ] The conditions under which each architecture document should be read are explicit.
- [ ] `apps/backend/AGENTS.md` follows the same conditional-read policy.
- [ ] `apps/admin/AGENTS.md` exists and contains concise Admin-specific coding, navigation, testing, and verification guidance.
- [ ] Canonical backend verification commands are directly discoverable in `apps/backend/AGENTS.md`.
- [ ] Canonical Admin verification commands are directly discoverable in `apps/admin/AGENTS.md`.
- [ ] Detailed backend testing guidance lives in `docs/engineering/backend-testing.md` and remains discoverable from backend guidance.
- [ ] Detailed Git/GitHub procedure lives in `docs/engineering/git-workflow.md` and is loaded only when Git operations are relevant.
- [ ] Root completion reporting is concise and does not require empty irrelevant sections.
- [ ] `.codex/tasks/TEMPLATE.md` defaults to root plus nearest scoped `AGENTS.md`, with architecture documents added conditionally.
- [ ] Existing Playwright/visual-regression template guidance is preserved.
- [ ] Historical task specs are not mass-edited.
- [ ] No production source, API, persistence, authentication, CI, dependency, or runtime behaviour changes.
- [ ] All referenced paths and commands exist in the current repository.
- [ ] The combined default backend `AGENTS.md` word count is reduced by at least 30%, or any smaller reduction is explicitly justified by a critical retained requirement.
- [ ] Core engineering, testing, security, compatibility, and verification standards remain enforceable after the reduction.

---

## Tests to add or update

No production unit or integration tests are required solely for documentation changes.

Perform documentation-contract verification instead.

Verify:

1. No stale backend architecture paths remain in the active architecture guidance.
2. Every path named in new Admin/backend guidance exists.
3. Every documented command exists in the corresponding package/configuration.
4. Root and backend AGENTS no longer require unconditional architecture-document loading.
5. The task template does not reintroduce unconditional architecture reads.
6. Extracted testing and Git guidance remain linked from the appropriate scoped/root documents.
7. Current visual-testing guidance in `.codex/tasks/TEMPLATE.md` remains intact.
8. No production code, migrations, lockfiles, or CI workflows changed.

If the repository has an existing documentation/link-validation command, run it. Do not introduce a new documentation framework solely for this PR.

---

## Verification commands

Run from repository root unless noted otherwise.

### Inspect changed files

```bash
git diff --check
git diff -- \
  AGENTS.md \
  apps/backend/AGENTS.md \
  apps/admin/AGENTS.md \
  .codex/tasks/TEMPLATE.md \
  docs/architecture/repository-map.md \
  docs/architecture/dependency-rules.md \
  docs/engineering/backend-testing.md \
  docs/engineering/git-workflow.md
```

### Confirm stale architecture paths are gone

```bash
rg 'apps/backend/app/' \
  AGENTS.md \
  apps/backend/AGENTS.md \
  docs/architecture \
  docs/engineering
```

Expected result: no obsolete architecture references.

If a historical/example reference is intentionally retained, document why.

### Inspect architecture-read policy

```bash
rg -n 'repository-map|dependency-rules' \
  AGENTS.md \
  apps/backend/AGENTS.md \
  apps/admin/AGENTS.md \
  .codex/tasks/TEMPLATE.md
```

Confirm architecture documents are conditional except where the task itself explicitly concerns architecture.

### Measure default backend guidance size

Before edits:

```bash
wc -w AGENTS.md apps/backend/AGENTS.md
```

After edits:

```bash
wc -w AGENTS.md apps/backend/AGENTS.md
```

Record baseline, final combined count, and percentage reduction.

### Backend commands documented by scoped guidance

From `apps/backend`:

```bash
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```

If the environment does not contain the required backend dependencies, verify the scripts/configuration statically and report the exact commands that could not be executed.

### Admin commands documented by scoped guidance

From repository root:

```bash
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
```

Only run commands that remain defined by the current Admin package.

### Final repository-scope check

```bash
git status -sb
git diff --name-only
```

Expected changed surface should remain limited to engineering guidance and task-template documentation.

---

## Exit criteria

The PR is complete when an ordinary backend task can obtain its governing engineering rules from:

```text
AGENTS.md
+
apps/backend/AGENTS.md
+
task-specific files
```

without automatically loading the full repository map, dependency rules, Git workflow, or detailed backend failure/test matrix.

Architecture-heavy, Git-heavy, security-heavy, persistence-heavy, or cross-application tasks must still have clear links to the additional guidance they need.

The resulting documentation must describe the repository that exists today rather than historical architecture, and the reduction in default context must not weaken coding, compatibility, testing, security, or verification standards.