# Redmoor Admin

Private React application for Redmoor administration. It provides cookie-backed administrator authentication and Assistant management for the supported identity and access fields. Knowledge Sources remains a placeholder; ingestion, evaluations, metrics, and operations are out of scope.

## Assistant management

Authenticated administrators can list and create Assistants at `/admin/assistants`, create at `/admin/assistants/new`, and edit at `/admin/assistants/:assistantId/edit`. The UI uses the protected backend `/admin/assistants` contract and supports only name, immutable slug, active/inactive status, and public/private visibility. Creation defaults to inactive/private. Updates use the backend concurrency token; deletion remains subject to seeded-assistant and dependency restrictions.

The feature deliberately excludes knowledge-source assignment, prompts, retrieval configuration, widget settings, preview, analytics, duplication, and bulk actions. Expired sessions return to login, malformed successful responses are rejected, and slug/update conflicts are presented without raw backend details.

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

Production hosting must rewrite browser-history routes such as `/admin/assistants` to `index.html`.
