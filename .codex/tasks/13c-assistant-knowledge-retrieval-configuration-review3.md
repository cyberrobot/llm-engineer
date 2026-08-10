PR 13C Follow-up 3 — Preserve Unknown Re-ingestion Identity and Finalize PR Verification

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

Do not broaden the scope beyond the two remaining review findings described below.

⸻

Governing specifications

Read and preserve the requirements from:

- .codex/tasks/13c-assistant-knowledge-retrieval-configuration.md
- .codex/tasks/13c-assistant-knowledge-retrieval-configuration-review1.md
- .codex/tasks/13c-assistant-knowledge-retrieval-configuration-review2.md

The existing implementation is substantially complete.

Do not rewrite or reimplement working functionality.

Preserve:

- Assistant-scoped knowledge-source routing;
- authenticated administrator behavior;
- runtime API validation;
- creation idempotency;
- re-ingestion idempotency;
- queued versus reused announcements;
- list and detail actions;
- retrieval enable/disable behavior;
- deletion handling;
- pagination correction;
- Assistant source-count refresh;
- focus restoration;
- safe error mapping;
- deterministic Storybook behavior;
- existing PR 13A and PR 13B workflows.

⸻

Objective

Resolve the final two findings from the latest review of PR #66:

1. An unknown-outcome re-ingestion operation can lose its retained idempotency identity if the administrator dismisses the dialog and later reopens it.
2. The PR description still reports the final GitHub Actions workflow as queued even though the final-head test workflow has completed successfully.

The final implementation must make an unknown re-ingestion outcome safe across dialog dismissal and must leave PR #66 with accurate verification evidence.

⸻

1. Preserve re-ingestion operation identity after an unknown outcome

Current problem

SourceActionDialog currently owns the re-ingestion idempotency key in a local ref similar to:

const reingestionKey = useRef<string | undefined>(undefined);

This works while the dialog remains mounted.

For a network failure or server failure where the mutation outcome is unknown:

- the key is correctly retained;
- the user can retry the identical request using that key;
- the backend can safely replay the logical operation.

However, the user can currently close or cancel the dialog.

Closing the dialog unmounts SourceActionDialog.

The retained key is then lost.

If the user immediately opens Re-ingest again, a new key is generated even though the previous operation may already have committed.

That turns an unknown-outcome retry into a new logical operation and may enqueue duplicate ingestion work.

⸻

Required behavior

A re-ingestion operation whose outcome is unknown must retain its logical identity until one of the following occurs:

- the identical operation succeeds using the retained idempotency key;
- the backend returns a definitive failure;
- authoritative source state is refreshed before a new re-ingestion operation begins.

The implementation must not allow dialog unmounting alone to silently convert an unknown operation into a new logical operation.

⸻

Preferred implementation

Move ownership of unresolved re-ingestion operations out of SourceActionDialog.

The parent knowledge-source view should own the retained operation state.

Use a focused state structure such as:

type ReingestionOperation = {
sourceId: string;
key: string;
outcome: 'unknown';
};

or equivalent.

The exact implementation may differ, but the lifetime of the retained key must extend beyond the lifetime of the dialog.

Do not use:

- localStorage;
- sessionStorage;
- query parameters;
- route parameters;
- visible UI text;
- logs;
- telemetry.

The retained operation only needs to survive normal React dialog dismissal while the current page remains mounted.

It does not need to survive a full page refresh.

⸻

Opening Re-ingest normally

When no unresolved operation exists for the source:

1. Open the confirmation dialog.
2. Generate a fresh opaque idempotency key when the logical re-ingestion operation begins.
3. Submit the request with that key.
4. Do not automatically retry.

⸻

Unknown outcome

Treat the following as unknown outcomes using the existing semantics:

- network failure;
- server/5xx failure where the request may already have committed.

After an unknown outcome:

- retain the source identifier;
- retain the exact idempotency key;
- show the existing safe unknown-outcome explanation;
- allow an explicit identical retry using the same key;
- do not silently generate a replacement key.

The user must not be able to accidentally trigger a new logical re-ingestion operation for the same source while the previous outcome remains unresolved.

⸻

Dialog dismissal after unknown outcome

Closing the dialog after an unknown outcome must be safe.

Implement one of these approaches.

Preferred approach

Allow dismissal, but preserve the unresolved operation in the parent.

If the user selects Re-ingest again for the same source:

- reopen the dialog in unresolved-operation mode;
- make it clear that the previous outcome is still unknown;
- reuse the retained idempotency key;
- offer the identical retry;
- do not generate a new key.

Also provide an explicit action to refresh authoritative source state.

Once authoritative state is successfully refreshed:

- clear the retained unresolved operation;
- any later Re-ingest action becomes a new logical operation and receives a fresh key.

Acceptable alternative

Prevent normal dialog dismissal while the operation outcome is unresolved, except through an explicit action that first refreshes authoritative source state.

Do not trap the administrator permanently in the modal if refresh fails.

If using this approach, preserve keyboard accessibility and provide a clear recovery path.

⸻

2. Authoritative refresh semantics

Add an explicit way to reconcile an unknown re-ingestion result with backend state.

The refresh must call the existing authoritative detail API.

For detail view:

GET /admin/assistants/{assistantId}/knowledge-sources/{sourceId}

For list view, use the existing authoritative list/detail reconciliation pattern as appropriate.

After a successful authoritative refresh:

- update the rendered source from the backend response;
- clear the retained unknown re-ingestion operation;
- close the unresolved operation UI if appropriate;
- announce that authoritative state has been refreshed;
- restore deterministic focus.

A subsequent Re-ingest action must generate a new key.

Do not infer success or failure merely from client state.

Do not assume a particular ingestion status proves whether the previous request was accepted unless the backend contract explicitly guarantees that.

The purpose of refresh is to end the unresolved client operation and return control to authoritative state.

⸻

3. Definitive failure behavior

Existing definitive failures must continue to clear the retained key.

Examples include:

- validation failure;
- forbidden;
- not found;
- idempotency conflict;
- other definitive contractual conflict responses.

Do not retain a key after a response that conclusively states the operation was not accepted as that logical request.

Preserve existing safe error handling.

Raw backend responses, provider messages, stack traces, HTML, database details and credentials must remain discarded.

⸻

4. Successful retry behavior

When an unknown re-ingestion is explicitly retried:

- use exactly the retained key;
- do not create a new logical operation;
- preserve duplicate-submission prevention;
- keep controls disabled while pending.

On successful 202:

- clear the retained operation;
- update the source from the authoritative response;
- preserve queued versus reused messaging;
- close the dialog;
- restore focus to the initiating action when it remains available.

A later independent Re-ingest action must generate a new key.

⸻

5. List and detail views must share the same safety rule

The same unknown-outcome lifecycle must apply whether the re-ingestion action starts from:

- the knowledge-source list; or
- the knowledge-source detail page.

Do not create two divergent idempotency rules.

Prefer extracting a small shared operation-state helper or passing retained operation state into the existing dialog if this keeps the behavior consistent.

Do not introduce a general-purpose mutation framework.

⸻

6. Accessibility and focus

Preserve all existing dialog accessibility behavior.

Required behavior:

- focus remains contained inside the modal while open;
- pending state remains announced;
- pending controls remain disabled;
- Escape and Cancel remain deterministic where allowed;
- reopening an unresolved operation gives the user clear context;
- successful identical retry restores focus to the original or equivalent stable re-ingestion trigger;
- authoritative refresh restores focus to a stable relevant control;
- no focus is left on an unmounted element;
- no state is communicated only through colour.

If the original initiating element no longer exists after an authoritative refresh, move focus to a stable source heading, source action, collection heading, or Add knowledge source control.

⸻

7. Regression tests

Add focused regression tests before or alongside the fix.

Extend:

apps/admin/src/App.test.tsx

Do not weaken existing tests.

Do not replace behavior tests with shallow implementation assertions.

⸻

Required unknown-outcome re-ingestion tests

Dialog dismissal preserves logical operation

Test:

1. Open Re-ingest.
2. Submit the operation.
3. Simulate a network or server unknown outcome.
4. Capture the idempotency key passed to reingestKnowledgeSource.
5. Dismiss the dialog.
6. Open Re-ingest again.
7. Retry the unresolved operation.
8. Assert the exact original key is reused.

The second interaction must not receive a newly generated key.

⸻

Multiple dismiss/reopen cycles

Test that repeated:

- open;
- dismiss;
- reopen

does not replace the unresolved operation key.

No new mutation should occur merely by reopening the dialog.

⸻

Refresh clears unresolved operation

Test:

1. Re-ingestion receives an unknown outcome.
2. Preserve the original key.
3. Perform the explicit authoritative refresh.
4. Confirm source detail/list is fetched again.
5. Start a later Re-ingest operation.
6. Confirm the new operation receives a different idempotency key.

⸻

Successful retry clears operation

Test:

1. First request has unknown outcome.
2. Reopen or remain in the dialog.
3. Retry using the same key.
4. Return successful 202.
5. Start another independent Re-ingest operation.
6. Verify the next operation receives a fresh key.

⸻

Definitive failure clears operation

For at least one definitive response such as:

idempotency_key_conflict

verify:

- the unresolved key is not retained as a retryable unknown operation;
- a later independent action can generate a fresh key;
- the UI gives the existing refresh guidance;
- the request is not automatically retried.

⸻

List and detail parity

Add coverage proving the safe lifecycle works from both list and detail interaction paths where practical.

At minimum, the shared operation state must be exercised through one path and the second path must have a regression assertion demonstrating it uses the same mechanism.

⸻

8. Preserve existing tests

The following existing behaviors must remain passing:

- creation unknown-outcome retry reuses the original key;
- changed creation payload generates a new key;
- re-ingestion retry while the dialog remains open reuses the key;
- re-ingestion pending state prevents duplicate submission;
- queued and reused re-ingestion results remain distinct;
- retrieval enable/disable focus restoration;
- Cancel and Escape focus restoration;
- active-ingestion deletion conflict;
- deletion pagination correction;
- Assistant-count refresh;
- mutation 401 expires the session;
- mutation 403 preserves the authenticated shell;
- source content and idempotency keys do not enter browser storage or URLs.

⸻

9. Do not change the backend contract

No backend production change is expected.

The existing backend already supports caller-owned idempotency keys for re-ingestion.

Do not add:

- a new endpoint;
- a new database field;
- a new persistence model;
- a new ingestion state;
- browser-generated reconciliation logic that substitutes for backend state.

If the existing backend contract unexpectedly cannot support this correction, stop and report the repository-state mismatch instead of implementing unrelated backend work.

⸻

10. Update PR #66 verification evidence

After the implementation is complete and all verification has been performed, update the existing PR #66 description.

The current description still states that GitHub Actions for the final head are queued.

Replace stale verification information with the actual final results.

The description must include:

- final branch/head SHA;
- concise summary of the PR 13C implementation;
- concise mention of this final unknown-outcome re-ingestion correction;
- exact local verification commands actually run;
- their actual pass/fail results;
- current GitHub Actions status for the final pushed head;
- explicit statement that live browser/backend-worker/PostgreSQL/manual ingestion scenarios were not run if they remain unperformed.

Do not claim a check succeeded until it has completed against the final pushed head.

If the PR head changes while implementing this correction, inspect the Actions workflow for the new final head rather than reporting results from 52bef88.

⸻

Acceptance criteria

- An unknown re-ingestion outcome retains its original idempotency key outside the dialog lifecycle.
- Cancelling or dismissing the dialog does not silently convert an unresolved operation into a new logical operation.
- Reopening Re-ingest for the same unresolved source reuses the retained operation identity.
- Identical retry uses exactly the original key.
- Unknown operation state can be reconciled through an explicit authoritative refresh.
- Successful authoritative refresh clears the unresolved operation.
- A later independent Re-ingest action receives a fresh key.
- Successful retry clears the unresolved operation and later independent work receives a fresh key.
- Definitive failures do not remain retryable as unknown outcomes.
- List and detail re-ingestion actions use the same operation lifecycle.
- No idempotency key is stored in localStorage, sessionStorage, URLs, logs or visible text.
- No automatic mutation retries are introduced.
- Existing queued/reused announcements remain correct.
- Existing dialog focus behavior remains deterministic.
- Existing Assistant, authentication, knowledge-list and source-detail tests remain passing.
- No backend production code, migrations or dependencies are changed.
- PR #66 description contains accurate verification results for the final head.
- Final GitHub Actions required checks pass.
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
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run lint:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
cd apps/backend
venv/bin/python -m pytest -q tests/test_knowledge_source_api.py
cd ../..
git diff --check
git status -sb

After pushing the final changes:

1. inspect PR #66;
2. confirm the PR head SHA matches the commit just verified locally;
3. inspect GitHub Actions for that exact SHA;
4. confirm all required checks complete successfully;
5. update the PR description with the actual results.

⸻

Out of scope

Do not add:

- backend production changes;
- migrations;
- new dependencies unless absolutely required to correct the existing frontend state lifecycle;
- file uploads;
- crawling;
- source editing;
- ingestion cancellation;
- retrieval-model configuration;
- chunking configuration;
- embedding controls;
- RAG UI changes;
- public widget changes;
- unrelated refactors;
- new general-purpose mutation/state-management frameworks.

Keep the patch narrowly focused on the final PR 13C review findings.

⸻

Completion report

When finished, report:

1. branch name and final head SHA;
2. files changed;
3. root cause of the unknown-outcome re-ingestion bug;
4. where unresolved operation ownership now lives;
5. how dialog dismissal/reopen behaves after an unknown outcome;
6. how authoritative refresh clears the unresolved operation;
7. regression tests added;
8. exact verification commands and results;
9. final GitHub Actions status for the exact final head;
10. confirmation that PR #66 description was updated;
11. confirmation that no backend production code, migration, dependency, RAG UI or public widget behavior changed;
12. any remaining deviations or risks.
