# PR 13A Follow-up — Address Review Findings

## Repository state

Expected branch:

`feature/13a-admin-application-foundation`

Base branch:

`main`

This work must be completed on the existing PR 13A branch. Do **not** create a new PR.

---

# Objective

Address the outstanding review findings identified during the implementation review of PR 13A.

This is a refinement task only. Do not introduce new functionality beyond the items listed below.

The objective is to ensure the Admin Application Foundation fully satisfies the original specification while improving maintainability, determinism and future extensibility.

---

# Required implementation

## 1. Remove generated Storybook output

The repository must not contain generated Storybook build artefacts.

Remove:

- `apps/admin/storybook-static/`

Remove the directory from Git tracking.

Add an appropriate ignore rule so future Storybook builds cannot accidentally be committed.

Prefer a reusable repository-wide rule where appropriate rather than an application-specific rule.

---

## 2. Make Storybook deterministic

Current Storybook stories instantiate the real API client and therefore attempt HTTP requests.

Stories must never depend on:

- network connectivity
- backend availability
- cookies
- browser session state
- DNS resolution

Replace all real API usage with deterministic fake implementations or the repository's established mocking infrastructure if one already exists.

Every story must explicitly define its authentication state.

Required scenarios:

### Login

- Default
- Pending
- Invalid credentials

### Session

- Session restoration loading
- Session restoration failure

### Shell

- Desktop authenticated
- Mobile authenticated

### Configuration

- Invalid configuration

No story should perform any network request.

No story should instantiate a real API client.

---

## 3. Improve authentication extensibility

The current authentication provider correctly restores sessions during application startup.

Extend the authentication foundation so future authenticated API calls can notify the application when the administrator session expires.

Examples include:

- sessionExpired()
- authentication invalidation callback
- shared authenticated request wrapper
- equivalent lightweight mechanism

Do not introduce unnecessary abstractions.

The goal is simply to avoid future PRs needing to replace or bypass the existing authentication provider.

---

## 4. Strengthen successful response validation

Current response validation verifies only the required fields.

Strengthen validation so malformed successful responses are rejected.

Validation should verify:

- expected top-level structure
- expected nested object structure
- expected primitive types
- absence of unexpected structural forms where appropriate

Malformed successful responses must continue to map to:

- `invalid_response`

Do not introduce a large validation framework unless one already exists within the repository.

---

## 5. Improve router integration

Replace any navigation that performs full browser reloads with React Router navigation.

Internal navigation should always remain client-side.

Review the application for any remaining `<a href>` navigation that should instead use the router.

---

## 6. Improve source readability

Several implementation files are compressed into dense single-line code.

Reformat the following modules using the repository formatting conventions:

- AuthProvider
- Admin API client
- Login page
- Application routing
- Admin shell

No behavioural changes should result from this work.

The goal is maintainability and reviewability.

---

# Tests

Extend existing tests where appropriate.

Add coverage for:

- malformed successful API responses
- session invalidation notifications
- deterministic Storybook authentication behaviour where supported

Existing tests must continue to pass.

---

# Acceptance criteria

- [ ] Generated Storybook build output is no longer committed.
- [ ] Storybook build output is ignored by Git.
- [ ] Storybook stories are completely deterministic.
- [ ] Stories perform no real HTTP requests.
- [ ] Authentication foundation supports future session invalidation.
- [ ] Malformed successful API responses are rejected.
- [ ] Internal navigation no longer performs browser reloads.
- [ ] Authentication and routing code follows repository formatting conventions.
- [ ] Existing tests continue to pass.
- [ ] Storybook builds successfully.
- [ ] Existing applications remain unaffected.

---

# Verification

Run the existing repository verification commands for the admin workspace.

Verify:

- lint passes
- type checking passes
- tests pass
- production build succeeds
- Storybook builds successfully
- existing frontend applications continue to build successfully
- no generated Storybook artefacts remain tracked by Git

Finish by running:

```bash
git diff --check
```
