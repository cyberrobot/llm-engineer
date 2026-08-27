# Redmoor Admin

Private React application for Redmoor administration. It provides cookie-backed administrator authentication, an operational Dashboard, detailed Operations, Assistant management, and Assistant-scoped knowledge and retrieval configuration. Evaluations and unsupported infrastructure administration remain out of scope.

## Operational Dashboard

The authenticated `/admin` route loads `GET /admin/operations/summary` once to show service health,
maintenance state, Assistant and Knowledge Source aggregates, ingestion state, workers observed,
cache-region count, operational jobs, and administrative activity today. It does not reconstruct
these values by loading lists or infrastructure-specific endpoints.

Conditions requiring attention are derived only from the current summary: non-healthy service state,
maintenance mode, failed operational or ingestion jobs, recoverable ingestion, queued ingestion with
no workers observed, and an authoritative non-zero Knowledge Source failure count. This is current
state, not an incident history. A null Knowledge Source failure count is shown as not reported.

The Dashboard supports manual refresh and safe retry without polling. An expired session follows the
existing login flow; forbidden, network, server, and malformed successful responses never render as
a healthy empty Dashboard.

## Detailed Operations

The `/admin/operations` landing page advertises only the detailed domains returned by the Operations
root capability response. Its nested routes provide health diagnostics, cache statistics and
confirmed cache administration, maintenance-mode inspection and confirmed updates, paginated job
browsing, and filtered paginated audit browsing. Job and audit detail routes render only the
backend's administrator-safe response fields.

All Operations calls use the shared credentialed Admin API client and strictly validate successful
responses. Production-affecting changes require scope-specific confirmation, are not automatically
retried, and refresh authoritative state after success. If the connection is lost after submission,
the UI reports the outcome as unknown and requires an authoritative refresh before another change.
Backend authorization remains authoritative; a forbidden response is never presented as healthy or
empty state. Cache keys are not persisted or logged, cache values are not exposed, and audit metadata
is rendered as inert data.

## Assistant management

Authenticated administrators can list and create Assistants at `/admin/assistants`, create at `/admin/assistants/new`, and edit at `/admin/assistants/:assistantId/edit`. The UI uses the protected backend `/admin/assistants` contract and supports only name, immutable slug, active/inactive status, and public/private visibility. Creation defaults to inactive/private. Updates use the backend concurrency token; deletion remains subject to seeded-assistant and dependency restrictions.

The Assistant identity form deliberately excludes knowledge-source fields, prompts, analytics, duplication, and bulk actions. Behaviour, preview, and knowledge use separate Assistant-scoped sections. Expired sessions return to login, malformed successful responses are rejected, and slug/update conflicts are presented without raw backend details.

## Behaviour, publishing, and preview

Open `/admin/assistants/:assistantId/behaviour` to edit the server-backed saved draft. The supported configuration is limited to instructions, welcome message, input placeholder, and up to eight ordered suggested questions. Instructions are generation guidance; the other fields are user-facing conversation text. Prompt whitespace is preserved, validation failures retain local values, and the backend concurrency token prevents a stale save from silently overwriting another administrator's work.

Saving a draft never publishes it. Publication is a separate confirmed operation that promotes the exact saved draft revision. Publication also does not activate the Assistant or change private/public visibility; those lifecycle controls remain on General. The page reports the authoritative published revision and whether the saved draft contains unpublished changes.

Open `/admin/assistants/:assistantId/preview` to exercise the saved draft through the authenticated backend preview contract. Preview uses the canonical Assistant widget conversation surface and the normal grounded generation pipeline, but it does not publish or change availability. Unsaved local Behaviour edits are not previewed. Preview conversation history exists only in component memory and Reset conversation clears it.

Behaviour prompts and preview conversations are never written to local storage, session storage, route URLs, or generic errors. The backend preview endpoint is required; the admin application does not fall back to public chat or browser-only prompt simulation.

## Knowledge and retrieval

Select an Assistant at `/admin/knowledge-sources` or open `/admin/assistants/:assistantId/knowledge`. Administrators can add direct text of up to 100,000 characters or one absolute HTTP(S) web page, inspect the latest asynchronous ingestion state, enable or disable the committed source for retrieval, request re-ingestion, and delete a source when ingestion is not active.

Source creation and re-ingestion use idempotency keys. If a network or server failure leaves an operation's outcome unknown, retrying the identical operation reuses its original key, including after dismissing and reopening the re-ingestion dialog. A changed or new creation is blocked until an explicit Assistant source-list refresh reconciles authoritative state; after that successful refresh, the later logical operation receives a fresh key. An explicit authoritative source-detail refresh similarly reconciles unknown re-ingestion before later work receives a new key. The interface reports whether creation or re-ingestion queued a new job or reused an existing canonical source or active job. Disabling retrieval preserves indexed content but excludes it from answers; enabling restores the currently committed representation without forcing re-ingestion.

Source detail includes the source timestamps and the complete supported lifecycle of its latest ingestion job. A failed ingestion retains its safe failure detail and may be retried after the underlying source is available; failure does not imply that the previous committed representation was removed.

Knowledge is strictly Assistant-scoped. List responses never contain direct-text bodies, successful responses are runtime validated, and source content is not written to browser storage or URLs. Cross-Assistant source identifiers use the same not-found presentation as unknown sources.

This interface does not support file upload, recursive crawling, source editing, ingestion cancellation, similarity thresholds, top-K, reranking, chunking, embedding selection, model configuration, chat preview, or retrieval debugging.

## Local development

From the repository root, run `npm ci`, copy `.env.example` to `.env.local`, and start the backend before running `npm run dev:admin`. The default Vite origin is `http://localhost:5173`; it must appear exactly in the backend `ADMIN_TRUSTED_ORIGINS` list because login/logout enforce Origin and CORS permits credentials. Set `VITE_ADMIN_API_BASE_URL=http://localhost:8000`; this browser-visible value is not a secret.

Create the first administrator only through the backend-supported `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` startup process documented in `apps/backend/docs/administrator-authentication.md`. Do not put credentials in frontend environment files.

The app checks `GET /admin/auth/me` before showing protected content. A confirmed missing or expired session goes to login; network/server failures retain an indeterminate state and offer retry. Login and logout use `credentials: "include"`; JavaScript never reads or persists the HTTP-only session cookie or password.

## Commands

Run `npm run dev:admin`, `npm run lint:admin`, `npm run typecheck --workspace @ai-discovery-assistant/admin`, `npm run test:admin`, `npm run build:admin`, or `npm run build-storybook --workspace=apps/admin` from the repository root.

## Troubleshooting

- A configuration screen means `VITE_ADMIN_API_BASE_URL` is missing or is not an absolute credential-free HTTP(S) URL.
- A restoration retry screen means the backend is unavailable or returned a server/malformed response.
- Browser CORS failures require the frontend origin in `ADMIN_TRUSTED_ORIGINS`; wildcard origins are incompatible with credentialed requests.
- Invalid, disabled, locked, or unknown accounts intentionally share the safe invalid-credentials response.
- A throttling message means the API returned its contractual `too_many_login_attempts` response; wait before retrying.
- An expired session is confirmed by the backend and returns to login. Reauthenticate rather than attempting to recover cookie data.
- A failed ingestion remains visible with the backend's safe failure message; correct the source outside this immutable-source workflow or retry re-ingestion where appropriate.
- An idempotency conflict requires refreshing authoritative state before starting a new logical operation.
- A source cannot be deleted while ingestion is queued or running. Wait for a terminal state, refresh, and try again.
- An invalid-response message means the backend returned a malformed or cross-Assistant success payload; the UI rejects it instead of rendering partial data.

Production hosting must rewrite browser-history routes such as `/admin/assistants` and `/admin/operations/jobs/:jobId` to `index.html`.
