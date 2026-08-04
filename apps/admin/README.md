# Redmoor Admin

Private React application foundation for Redmoor administration. It currently provides cookie-backed administrator login, session restoration, logout, protected routing, and honest Dashboard, Assistants, and Knowledge Sources placeholders. Management workflows, account management, ingestion, evaluations, metrics, and operations are explicitly out of scope.

## Local development

From the repository root, run `npm ci`, copy `.env.example` to `.env.local`, and start the backend before running `npm run dev:admin`. The default Vite origin is `http://localhost:5173`; it must appear exactly in the backend `ADMIN_TRUSTED_ORIGINS` list because login/logout enforce Origin and CORS permits credentials. Set `VITE_ADMIN_API_BASE_URL=http://localhost:8000`; this browser-visible value is not a secret.

Create the first administrator only through the backend-supported `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` startup process documented in `apps/backend/docs/administrator-authentication.md`. Do not put credentials in frontend environment files.

The app checks `GET /admin/auth/me` before showing protected content. A confirmed missing or expired session goes to login; network/server failures retain an indeterminate state and offer retry. Login and logout use `credentials: "include"`; JavaScript never reads or persists the HTTP-only session cookie or password.

## Commands

Run `npm run dev:admin`, `npm run lint --workspace @ai-discovery-assistant/admin`, `npm run typecheck --workspace @ai-discovery-assistant/admin`, `npm run test:admin`, `npm run build:admin`, or `npm run storybook --workspace @ai-discovery-assistant/admin` from the repository root.

## Troubleshooting

- A configuration screen means `VITE_ADMIN_API_BASE_URL` is missing or is not an absolute credential-free HTTP(S) URL.
- A restoration retry screen means the backend is unavailable or returned a server/malformed response.
- Browser CORS failures require the frontend origin in `ADMIN_TRUSTED_ORIGINS`; wildcard origins are incompatible with credentialed requests.
- Invalid, disabled, locked, or unknown accounts intentionally share the safe invalid-credentials response.
- A throttling message means the API returned its contractual `too_many_login_attempts` response; wait before retrying.
- An expired session is confirmed by the backend and returns to login. Reauthenticate rather than attempting to recover cookie data.

Production hosting must rewrite browser-history routes such as `/admin/assistants` to `index.html`.
