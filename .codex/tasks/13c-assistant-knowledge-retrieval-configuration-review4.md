PR 13C Follow-up 4 — Align Final Implementation with Original Specification

Repository state

Repository:

cyberrobot/llm-engineer

Existing pull request:

#66 — Add assistant knowledge retrieval configuration

Branch:

feature/13c-assistant-knowledge-retrieval-configuration

Base branch:

main

Continue work on the existing PR #66 branch.

Do not create a new branch or pull request.

Do not broaden the implementation beyond the remaining original PR 13C deviations described below.

⸻

Governing specification

The authoritative specification for this correction is:

.codex/tasks/13c-assistant-knowledge-retrieval-configuration.md

Also read the existing corrective specs to preserve already-completed fixes:

- .codex/tasks/13c-assistant-knowledge-retrieval-configuration-review1.md
- .codex/tasks/13c-assistant-knowledge-retrieval-configuration-review2.md
- .codex/tasks/13c-assistant-knowledge-retrieval-configuration-review3.md

Where a later follow-up is looser than the original PR 13C requirement, the original PR 13C specification is authoritative.

Preserve all working functionality already implemented.

⸻

Objective

Resolve the remaining deviations found when reviewing PR #66 against the original PR 13C specification.

The required corrections are:

1. Prevent a changed creation payload from becoming a new logical operation immediately after an unknown create outcome without first reconciling authoritative state.
2. Complete the destructive deletion confirmation wording required by the original specification.
3. Make the authoritative re-ingestion recovery read abortable and lifecycle-safe.
4. Add the remaining explicitly required rendered regression cases.
5. Refresh the PR verification evidence for the final head.

No backend production change is expected.

⸻

1. Reconcile unknown creation outcomes before allowing changed/new creation

Current problem

KnowledgeSourceCreatePage correctly retains the original creation idempotency key while the payload remains identical.

However, after an unknown outcome, editing any field currently clears the retained operation:

operationRef.current = undefined;
setUnknownOutcome(false);

A subsequent submission then receives a new crypto.randomUUID() immediately.

This violates the original PR 13C rule:

- an unknown operation may be retried only with the same key and identical payload;
- otherwise the administrator must refresh authoritative state before beginning another logical operation.

The first create request may already have committed even though the response was lost.

A changed payload must therefore not silently start a new source creation while the previous outcome remains unresolved.

⸻

Required behavior

After a create mutation receives an unknown outcome:

- retain the original logical operation;
- retain the exact submitted payload fingerprint;
- retain the exact idempotency key;
- preserve the administrator’s form values;
- show a safe outcome-unknown message;
- allow an explicit identical retry using the same key;
- provide an explicit authoritative reconciliation action.

The user must not be able to submit a changed or new create request until authoritative reconciliation has occurred.

⸻

Form editing after an unknown outcome

The form may remain editable if that provides the better UX, but editing must not clear the unresolved operation automatically.

If any field differs from the unresolved submitted payload:

- make it clear that the pending unknown operation cannot be retried with the modified payload;
- disable normal create submission until authoritative reconciliation is completed;
- do not reuse the old key with the changed payload;
- do not create a new key yet.

An implementation may alternatively lock mutation-relevant fields while unresolved, provided the user has a clear way to reconcile authoritative state and the form remains accessible.

Do not silently discard the unresolved operation merely because a field changed.

⸻

2. Add authoritative reconciliation for unknown creation

Required recovery path

Add an explicit action such as:

Refresh authoritative state

or another precise equivalent.

The purpose is to resolve the client-side uncertainty before permitting a new logical operation.

Use the existing authenticated backend APIs.

Because the create result may have produced a new source whose identifier is unknown to the browser, authoritative reconciliation should refresh the Assistant’s source collection rather than rely on an unknown source ID.

Use the canonical Assistant-scoped list endpoint:

GET /admin/assistants/{assistantId}/knowledge-sources

Use the existing API client and runtime validation.

Do not add a backend endpoint.

⸻

After successful reconciliation

After the authoritative list is successfully fetched:

- clear the unresolved creation operation;
- keep the current form values unless there is a clear reason not to;
- announce that authoritative state was refreshed;
- allow the administrator to submit a changed/new logical operation;
- that later operation must receive a fresh idempotency key.

Do not infer whether the previous create succeeded unless the returned authoritative state proves it according to the existing contract.

The UI does not need to automatically identify the exact created source if there is no safe deterministic way to do so.

The important invariant is that a new key is not issued until authoritative state has been reconciled.

⸻

Reconciliation failure

If authoritative refresh fails:

- retain the unresolved operation;
- keep identical retry available;
- keep changed/new submission blocked;
- show a safe retryable refresh error;
- preserve all form values;
- do not expose raw backend details.

A confirmed 401 must continue to expire the session through the existing authentication mechanism.

A 403 must preserve the authenticated session.

⸻

3. Creation idempotency lifecycle

The final creation lifecycle must be:

New operation

Generate one fresh opaque idempotency key immediately before the first submission.

Pending

Prevent duplicate submissions.

Success

Clear the retained operation and continue with canonical navigation and queued/reused announcement.

Unknown outcome

Retain:

- payload fingerprint;
- idempotency key;
- unresolved status.

Permit only:

- identical retry with the same key;
- authoritative reconciliation.

Identical retry

Reuse the exact original key.

Payload changes during unresolved state

Do not generate a new key.

Do not submit.

Require authoritative reconciliation first.

Successful reconciliation

Clear the unresolved operation.

A later submission receives a new key.

Definitive failure

Clear the unresolved operation when the server conclusively rejected the logical request, including contractual validation or idempotency conflict responses.

Do not automatically retry mutations.

⸻

4. Add regression tests for unknown create reconciliation

Extend:

apps/admin/src/App.test.tsx

Add focused behavior tests.

⸻

Changed payload remains blocked after unknown outcome

Test:

1. Submit a valid direct-text creation.
2. Return AdminApiError('network') or AdminApiError('server').
3. Capture the original idempotency key.
4. Modify the name or direct text.
5. Attempt submission.
6. Assert no second create request is made.
7. Assert the UI explains that authoritative state must be refreshed before starting a changed operation.

⸻

Identical retry still reuses original key

Preserve existing coverage:

1. unknown outcome;
2. retry identical request;
3. exact original key is reused.

Do not regress this behavior.

⸻

Successful authoritative refresh permits fresh operation

Test:

1. create receives unknown outcome;
2. modify the form;
3. perform authoritative source-list refresh;
4. confirm the list API is called for the same Assistant;
5. submit the changed payload;
6. assert a fresh idempotency key is used;
7. assert it differs from the unresolved operation key.

⸻

Failed authoritative refresh preserves unresolved state

Test:

1. unknown create outcome;
2. authoritative list refresh fails;
3. changed/new create submission remains blocked;
4. identical retry still uses the original key;
5. form content remains present.

⸻

Sensitive data remains absent

Preserve or extend assertions that:

- idempotency keys are not placed in URLs;
- direct text is not stored in localStorage/sessionStorage;
- source content is not added to route URLs;
- reconciliation does not persist form data outside component state.

⸻

5. Complete deletion confirmation wording

Current problem

The current delete dialog identifies the source and explains that its owned indexed representation will be removed.

The original specification also requires the confirmation to explain that deletion is blocked while ingestion is queued or running.

⸻

Required wording

Update the deletion confirmation so it clearly communicates both semantics:

- deletion removes the source and its owned indexed representation;
- deletion cannot complete while ingestion is active.

Example meaning:

Delete Policy guide and its owned indexed representation? Deletion is blocked while ingestion is active.

Exact wording may differ.

Do not imply that the frontend decides whether deletion is allowed.

The backend remains authoritative.

⸻

Regression coverage

Update the deletion confirmation Storybook play assertion and/or rendered test to verify:

- source name appears;
- owned indexed representation is mentioned;
- active ingestion restriction is communicated before mutation.

Preserve existing active-ingestion conflict handling.

⸻

6. Make authoritative re-ingestion refresh abortable

Current problem

The unresolved re-ingestion recovery path currently calls:

auth.api.getKnowledgeSource(assistantId, source.id)

without an AbortSignal.

The original PR 13C state/cancellation requirements require superseded detail reads to be abortable and ignored on navigation/unmount.

⸻

Required behavior

The authoritative re-ingestion refresh must:

- create an AbortController;
- pass controller.signal to getKnowledgeSource;
- abort when the recovery operation is superseded or the component/dialog lifecycle ends where appropriate;
- ignore AbortError;
- never present an aborted request as a user-facing failure;
- prevent stale completion from updating an unmounted or superseded UI.

Do not add a new polling or request framework.

Use the existing request/cancellation style from list/detail loading.

⸻

Preferred shape

Keep cancellation ownership at the page/component level if practical rather than burying it in a generic helper.

The implementation may use a small dedicated helper or ref if needed.

Do not introduce a general query/cancellation abstraction solely for this correction.

⸻

7. Add missing rendered ingestion-state regressions

The original PR 13C test matrix explicitly requires rendered coverage for the following states.

Extend:

apps/admin/src/App.test.tsx

⸻

No ingestion job

Render source detail with:

latestIngestion: null

Assert the safe no-job presentation is shown.

For example:

No ingestion job was reported.

Do not fabricate progress or status.

⸻

Cancelled ingestion

Render source detail with:

status: 'cancelled'

Assert:

- Cancelled is rendered as a readable textual status;
- no unsupported recovery claim is shown;
- the source detail remains usable.

⸻

8. Add direct-text HTML escaping regression

The original specification explicitly requires direct text to be rendered as text rather than interpreted HTML.

Add a rendered regression using fictional malicious-looking content such as:

<img src=x onerror="alert('x')"><script>bad()</script>

Assert:

- the literal content is visible as text;
- no <img> element is created from that string;
- no <script> element is created from that string;
- the content remains inside the read-only source presentation.

Do not use real sensitive content.

This test should verify observable rendered behavior rather than React implementation details.

⸻

9. Preserve existing runtime and API-boundary behavior

Do not regress:

- exact Assistant-scoped knowledge paths;
- credentials: 'include';
- AbortSignal forwarding;
- runtime source validation;
- Assistant ownership validation;
- list omission of direct text;
- URL scheme/credential/fragment validation;
- ingestion status and step enum validation;
- malformed response rejection;
- 202 creation/re-ingestion enforcement;
- 204 deletion enforcement;
- safe failure mapping;
- raw response-body discarding;
- caller-owned idempotency keys;
- safe re-ingestion unknown-outcome persistence;
- active-job reuse messaging;
- Assistant-count refresh;
- final-page deletion correction.

No backend production change is expected.

⸻

10. Preserve accessibility

Maintain existing accessible behavior.

Requirements:

- error summary remains focusable and receives focus where appropriate;
- unresolved creation state is announced;
- blocked create action is understandable to keyboard and screen-reader users;
- reconciliation pending state is announced;
- controls are disabled while pending;
- delete confirmation remains source-specific;
- dialog focus containment and restoration remain deterministic;
- ingestion states do not rely on colour;
- long direct text and URLs continue to wrap safely.

Do not add a second dialog system.

⸻

11. Storybook

Update deterministic stories only where needed.

At minimum update or add coverage for:

- deletion confirmation including active-ingestion restriction;
- no-ingestion detail, if useful;
- cancelled ingestion detail, if useful.

Stories must remain:

- network-free;
- cookie-independent;
- deterministic;
- based on fixed fictional identifiers/content;
- independent of current time;
- free of shared mutable state.

No new story is required for creation authoritative reconciliation if the rendered application tests cover it well.

⸻

12. Documentation

Update apps/admin/README.md to accurately describe unknown creation recovery.

Current documentation says changed creation fields become a new logical operation with a new key.

Replace that behavior with the original-spec rule:

- an unknown create operation may be retried only with the identical payload and same key;
- changed/new creation is blocked until authoritative source state has been refreshed;
- after successful reconciliation, a new logical operation receives a fresh key.

Also preserve documentation for:

- re-ingestion unknown-outcome recovery;
- retrieval enable/disable;
- deletion conflict;
- failed ingestion;
- scope exclusions.

⸻

13. Update PR #66 verification evidence

After all changes are complete, update PR #66’s description.

The current PR head at the time of this review was:

498bb67acc92ee0fb97bb5ccaff6676c4fee4102

Do not assume that remains the final head after this corrective work.

After pushing the final correction:

1. resolve the new final head SHA;
2. inspect GitHub Actions for that exact SHA;
3. report only completed results.

The current 498bb67 workflow completed successfully for:

- Storybook tests;
- Backend tests.

The PR body must no longer claim that the earlier 52bef88 workflow is queued.

⸻

Required PR description content

Include:

- concise PR 13C summary;
- mention of unknown-create authoritative reconciliation;
- mention of unknown re-ingestion operation preservation;
- exact local commands actually run;
- actual pass/fail counts;
- final GitHub Actions results for the exact final head;
- explicit manual-test limitations.

Do not claim live administrator/backend-worker/manual ingestion scenarios were performed unless they actually were.

⸻

Acceptance criteria

- Unknown create outcomes retain their payload fingerprint and idempotency key.
- Identical explicit retry uses the exact original create key.
- Editing a form after an unknown outcome does not silently clear the unresolved operation.
- A changed/new create request cannot be submitted until authoritative state is reconciled.
- Authoritative reconciliation uses the real Assistant-scoped source list API.
- Failed reconciliation leaves the unresolved create operation intact.
- Successful reconciliation clears it and a later operation receives a fresh key.
- No mutation is automatically retried.
- No idempotency key or source content enters URLs or browser storage.
- Delete confirmation explains both destructive removal and active-ingestion blocking.
- Re-ingestion authoritative recovery reads are abortable.
- Aborted recovery reads do not display spurious errors.
- Rendered regression coverage exists for no-ingestion state.
- Rendered regression coverage exists for cancelled ingestion.
- Direct-text HTML-looking content is rendered only as text.
- Existing queued/running/completed/failed ingestion presentation remains passing.
- Existing Assistant, authentication, knowledge-list, retrieval, re-ingestion and deletion tests remain passing.
- Storybook remains deterministic and network-free.
- No backend production code, migration, dependency, RAG UI or public widget behavior changes.
- Admin lint, type-check, tests, production build and Storybook build pass.
- Backend knowledge-source regression tests pass.
- Final GitHub Actions required checks pass for the exact final head.
- PR #66 description contains current verification evidence.
- git diff --check passes.

⸻

Verification commands

Run from the repository root.

git status -sb
git branch --show-current
git rev-parse HEAD
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx
npm test --workspace @ai-discovery-assistant/admin -- src/api/adminApi.test.ts
npm run test:admin
npm run lint:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
cd apps/backend
venv/bin/python -m pytest -q tests/test_knowledge_source_api.py
cd ../..
git diff --check
git status -sb

If repository script names differ, use the documented equivalents and report the exact commands actually executed.

After pushing:

1. obtain the exact final head SHA;
2. inspect GitHub Actions for that SHA;
3. verify required jobs completed successfully;
4. update PR #66 description with the final results.

⸻

Out of scope

Do not add:

- backend production changes;
- migrations;
- new source types;
- file upload;
- crawling;
- source editing;
- ingestion cancellation;
- polling;
- similarity controls;
- top-K controls;
- chunking controls;
- embedding/model configuration;
- RAG UI changes;
- public Assistant widget changes;
- unrelated refactors;
- general-purpose request/state frameworks.

Keep the final patch narrowly focused on original PR 13C compliance.

⸻

Completion report

When finished, report:

1. branch and final head SHA;
2. files changed;
3. root cause of the unknown-create deviation;
4. how unresolved create state is now retained;
5. how authoritative reconciliation works;
6. how changed/new creation is blocked before reconciliation;
7. delete confirmation correction;
8. abortable re-ingestion refresh correction;
9. regression tests added for no-job, cancelled and HTML-as-text behavior;
10. exact verification commands and results;
11. final GitHub Actions status for the exact final head;
12. confirmation that PR #66 description was updated;
13. manual scenarios performed versus not run;
14. confirmation that no backend production code, migration, dependency, RAG UI or public widget behavior changed;
15. any remaining deviations or risks.
