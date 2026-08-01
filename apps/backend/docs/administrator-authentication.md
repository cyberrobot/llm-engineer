# Administrator authentication

The administrator API uses persistent accounts and revocable server-managed sessions. It is
separate from assistant visibility and the existing operations API-key authorization.

## Bootstrap

Set both `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` to create the initial account at
application startup after database migrations run. Emails are trimmed, lowercased, validated, and
stored under a matching database normalization constraint. Passwords must contain 12–1024
characters and are stored with `argon2-cffi`'s Argon2id defaults, including a library-generated
salt.

Bootstrap is idempotent under the unique email constraint. A repeated startup preserves the
existing password hash, status, lockout state, and sessions. A production deployment with no
configured bootstrap credentials starts only when an administrator already exists; otherwise it
fails closed. Development and test environments deliberately do nothing when credentials are
absent. Never commit or log a real bootstrap password. After the first production bootstrap, the
two variables may be removed because the persisted administrator satisfies the startup check.

## HTTP contract

All responses use `Cache-Control: no-store` and `Pragma: no-cache`. Errors use the established
`detail.code` and `detail.message` envelope.

- `POST /admin/auth/login` accepts `{"email":"admin@example.com","password":"..."}`. Success is
  `200` with `{"user":{"id":"...","email":"admin@example.com","role":"administrator"}}` and an
  HTTP-only cookie. Invalid credentials (including unknown, disabled, or locked accounts) return
  `401 invalid_credentials`; validation returns `400 invalid_request`; throttling returns
  `429 too_many_login_attempts` with `Retry-After`.
- `GET /admin/auth/me` restores the session and returns the same user representation. Missing,
  invalid, expired, revoked, deleted-account, and disabled-account sessions return
  `401 authentication_required`.
- `POST /admin/auth/logout` revokes the current server-side session, clears the cookie, and returns
  `204`. Missing, invalid, or already-revoked sessions remain successful.

The OpenAPI schema declares `AdministratorSessionCookie` as an API-key cookie security scheme.
PR 13A should call these routes with browser credentials enabled (`credentials: "include"`) and
should use `/admin/auth/me` as the canonical refresh/session-restoration source. Session tokens are
never returned in JSON or exposed to browser JavaScript.

## Sessions and cookies

A login generates 256 bits of randomness with Python's cryptographic `secrets` API. Only the raw
opaque token enters the browser cookie; PostgreSQL stores its SHA-256 lookup digest. Session rows
have an absolute expiry and revocation timestamp. Validation joins the session to the current
administrator on every request and requires an active account. `last_seen_at` is updated no more
than once every five minutes. A bounded cleanup during login removes expired and revoked rows;
expired rows never authorize before cleanup.

Configuration:

- `ADMIN_SESSION_TTL_SECONDS` (default `28800`, eight hours)
- `ADMIN_SESSION_COOKIE_NAME` (default `redmoor_admin_session`)
- `ADMIN_SESSION_COOKIE_SECURE` (default false only in development; production requires true)
- `ADMIN_SESSION_COOKIE_SAMESITE` (`lax` by default; `lax` or `strict`)

The cookie always uses `HttpOnly`, `Path=/`, `SameSite`, `Max-Age`, and `Expires`. Logout clears it
with matching path, secure, HTTP-only, and same-site attributes.

## CSRF, origins, and CORS

Cookie-authenticated state changes use reusable strict Origin validation. Login, logout, and future
administrator mutations must supply an exact origin listed in `ADMIN_TRUSTED_ORIGINS`. Requests
with a missing or untrusted Origin receive `403 forbidden`. The same list configures credentialed
CORS; wildcard origins are not used. The defaults support `http://localhost:5173` and the same-site
production frontend. Non-browser scripts must deliberately send an allowed `Origin` header.

Future routes should depend on `require_authenticated_administrator` to load an active account and
on `require_administrator_role` for the constrained `administrator` role. State-changing routes
must also depend on `require_trusted_admin_origin`.

## Brute-force controls

The existing `limits`/Redis stack applies fixed-window limits by source IP, normalized-email hash,
and a global key. No email or IP labels enter metrics. Configure:

- `ADMIN_LOGIN_THROTTLE_WINDOW_SECONDS` (default `60`)
- `ADMIN_LOGIN_THROTTLE_IP_ATTEMPTS` (default `20`)
- `ADMIN_LOGIN_THROTTLE_EMAIL_ATTEMPTS` (default `10`)
- `ADMIN_LOGIN_THROTTLE_GLOBAL_ATTEMPTS` (default `200`)
- `ADMIN_LOGIN_MAX_FAILURES` (default `5`)
- `ADMIN_LOGIN_LOCKOUT_SECONDS` (default `900`)

Failed-password counter updates and the threshold lockout happen under a PostgreSQL row lock.
Attempts during lockout do not verify the stored password. Lockout expires automatically, and the
next successful login resets both failure fields. Unknown, disabled, and locked identities take a
valid dummy Argon2 verification path and receive the same external response. Setting the existing
`DISABLE_RATE_LIMITS=true` disables throttling only for explicitly configured local/test use.

Structured logs record bounded security event names and safe IDs or email digests, never plaintext
passwords, hashes, raw tokens, cookies, or request bodies. Prometheus exposes bounded login attempt,
success, failure, throttle, session-created, and session-revoked counters.
