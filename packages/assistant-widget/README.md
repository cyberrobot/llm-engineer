# @redmoor/assistant-widget

An inline React widget for the public Redmoor assistant API. The package owns the accessible
conversation interface, bounded in-memory state, request lifecycle, safe error messages, and
manual retry behavior. The consuming application owns placement and runtime configuration.

## Installation

```sh
npm install @redmoor/assistant-widget
```

The repository uses npm workspaces. Consumers using another package manager can install the same
version with its normal package-add command.

## Usage

Import the component and the compiled stylesheet through the supported package exports:

```tsx
import { AssistantWidget } from '@redmoor/assistant-widget'
import '@redmoor/assistant-widget/styles.css'

export function AssistantSection() {
  return (
    <AssistantWidget
      assistantId="redmoor"
      apiBaseUrl="https://api.example.com"
    />
  )
}
```

The package also exports `AssistantWidgetConversation` and the `AssistantChatClient` contract as an additive integration boundary for trusted applications that need the canonical conversation UI with a different server-backed transport. Existing custom clients may continue to implement `send()`. Clients that also implement the optional `stream()` method can surface ordered response deltas through `onDelta`; the conversation updates one in-progress Assistant message and commits it to history only after successful completion. The standard `AssistantWidget` continues to construct and use the public chat client; custom clients must enforce their own authentication and server-side authorization.

The stylesheet is compiled and locally scoped. Consumers do not need Tailwind, PostCSS, CSS
Modules, or other widget-specific styling configuration.

## Props

| Prop | Type | Required | Behavior |
| --- | --- | --- | --- |
| `assistantId` | `string` | Yes | Public assistant slug placed in the API route. |
| `apiBaseUrl` | `string` | Yes | Public API origin or base path. A trailing slash is accepted. |
| `assistantName` | `string` | No | Explicit visible and accessible name override. |
| `welcomeMessage` | `string` | No | Explicit initial-message override; `""` intentionally hides the published welcome text. |
| `placeholder` | `string` | No | Explicit composer-placeholder override. |
| `suggestedQuestions` | `readonly string[]` | No | Explicit suggestion override; `[]` intentionally hides published suggestions. |

The root export also provides the component props, conversation client and streaming option types,
the safe chat error, and the shared SSE consumer. Internal transport implementations, reducers,
hooks, and UI components are not public API.

## Behavior

On mount, the widget calls `GET /public/assistants/{assistantId}` without credentials and validates
the response before rendering the conversation. The Assistant's currently published configuration
provides its name, welcome message, input placeholder, and ordered suggested questions. A saved
draft is not visible until an administrator publishes it; a remount or page reload retrieves the
latest published revision. `assistantId` is the public, route-safe Assistant slug, not its internal
backend UUID.

Optional presentation props are deliberate embedding-specific overrides. For each prop, an
explicit value takes precedence over the published server value, using `undefined` to mean “no
override.” Overrides never bypass the bootstrap availability check. Missing, inactive, or private
Assistants show the same safe unavailable state. Network and malformed-response failures show safe
configuration errors and do not fall back to potentially stale host presentation.

Conversations live only in the current widget instance and are never persisted. After bootstrap,
the widget calls `POST /public/assistants/{assistantId}/chat` without authentication, sends bounded
completed conversation history, incrementally renders validated SSE deltas, and permits one request
at a time. The chat endpoint independently rechecks availability for every question. Supported
transient failures show a safe message and a manual retry action; backend response bodies and raw
transport errors are not exposed or logged. Active bootstrap and chat requests are aborted when the
widget unmounts or its API configuration changes.

React and React DOM are peer dependencies. The supported range is React 19, matching the
repository's tested React version. The ESM package can be imported during server rendering;
browser-only APIs are accessed after mount or when a user sends a question.

## Current limitations

The package does not include citations, persisted conversations,
conversation restoration, attachments, authentication, analytics, a floating launcher, iframe or
script-tag embedding, arbitrary white-label theming, or framework-specific wrappers.

## Local development

From the repository root:

```sh
npm install
npm run dev:assistant
npm run test --workspace @ai-discovery-assistant/assistant-demo
npm test --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
```

The private Vite demo lives in `apps/assistant-demo` and imports the widget through
`@redmoor/assistant-widget`. The package-consumer fixture remains beside the package. Neither is
included in the published tarball.

## Releasing

Changesets owns package versions, changelog updates, publication, and release tags. Do not edit the
widget version or create a release tag manually.

For every pull request that changes the published widget contract or artifact:

1. Run `npm run changeset`, select `@redmoor/assistant-widget`, and choose the appropriate semantic
   version impact.
2. Edit the generated summary so it describes the consumer-visible change, then commit the
   `.changeset/*.md` file with the implementation.
3. Run the widget lint, tests, build, and `pack:verify` checks before merging.

After the pull request merges to `main`, the **Release assistant widget** workflow verifies the
package and creates or updates the Changesets Release PR. Review and merge that Release PR to apply
the calculated package version, lockfile, and changelog changes. The same workflow then publishes
the unpublished widget through `changeset publish` and creates the standard
`@redmoor/assistant-widget@<version>` tag and GitHub release. `workflow_dispatch` runs this same path;
it does not bypass the Release PR state or quality gates. Select the `main` branch when dispatching
the workflow manually; the release job does not run for any other branch or tag.

Pull-request CI is path-scoped to the widget package and its release inputs. Those inputs include
the root npm manifests, Changesets files, and the widget CI and publishing workflows; changes to
them can affect workspace dependency resolution or publication even when widget source is
unchanged. The **Assistant widget validation** check appears only on pull requests that change one
of these paths. When it appears, checkout, dependency installation, workflow-configuration
verification, applicable Changesets enforcement, lint, tests, build, and package verification all
run.

Unrelated application, backend, documentation, and task-only pull requests do not receive an
Assistant widget validation check. This workflow does not configure GitHub repository rules.
Repository administrators should not make the path-scoped check universally required because an
unrelated pull request does not create it. Pushes to `main` continue to run all widget quality gates
for release safety.

The canonical same-repository `changeset-release/main` PR is exempt from the Changeset requirement
because `changeset version` has already consumed its pending Changesets into the version and
changelog. Widget lint, tests, build, and package verification still run on the Release PR. A fork
cannot obtain this exemption merely by using the same branch name.

Before the first release, configure npm trusted publishing for `@redmoor/assistant-widget` with the
GitHub repository owner and name, workflow filename `publish-assistant-widget.yml`, environment
`npm`, and permission to run `npm publish`. Create the matching GitHub environment. In GitHub, open
**Settings → Actions → General → Workflow permissions** and enable **Allow GitHub Actions to create
and approve pull requests**. Despite the setting's broad label, this workflow uses the permission to
create or update the Changesets Release PR; merging that PR remains a human action. Repository
administrators can verify the setting without changing it with:

```sh
gh api repos/OWNER/REPOSITORY/actions/permissions/workflow
```

`can_approve_pull_request_reviews` must be `true`. The workflow keeps the repository's default token
permission read-only and grants only `contents: write`, `pull-requests: write`, and `id-token: write`
for the release job. It uses GitHub OIDC and no long-lived npm token. Publishing uses the public
registry and npm provenance.

If the action reports that GitHub Actions is not permitted to create pull requests, enable the
repository setting above and rerun the failed workflow. A failed attempt can leave
`changeset-release/main` without an open pull request; do not delete the pending Changeset, edit
versions, or create a second release branch. Rerunning the same workflow updates that canonical
branch and creates the single Release PR.

If a package check fails, fix it in a reviewed pull request and let Changesets update the Release PR.
If publication fails before npm accepts the version, correct the trusted-publisher or environment
configuration and rerun the failed workflow or dispatch the workflow from `main`. Changesets skips
versions already present on npm; never move an existing release tag or edit a released version.

### Connected backend demo

The primary Vite demo is a real consumer of the minimum package-level `AssistantWidget` API. It
loads published presentation from the backend, uses the same public chat client as a host
application, keeps conversation history in memory, and never stores or logs questions and answers.
Only automated tests intercept HTTP; normal local use requires a running backend.

Create `apps/assistant-demo/.env` from `apps/assistant-demo/.env.example`:

```dotenv
VITE_ASSISTANT_API_BASE_URL=http://localhost:8000
VITE_ASSISTANT_ID=redmoor
```

Both values are required. The demo deliberately has no localhost or assistant fallback, so a
production build cannot silently connect to a developer machine. These are public browser settings,
not secrets.

For the smallest seeded local setup, configure `apps/backend/.env` with
`PUBLIC_ASSISTANT_CHAT_ENABLED=true`, a valid `OPENAI_API_KEY`, and an empty `DATABASE_URL`. The
backend then uses its built-in active, publicly visible `redmoor` assistant and curated in-memory
knowledge fixture. Start the backend and frontend from separate repository-root terminals:

```sh
source apps/backend/venv/bin/activate
npm run dev:api
```

```sh
npm run dev:assistant
```

Open `http://localhost:5173`, submit a suggested or manual question, and verify that the response
appears. A follow-up sends the completed prior turn through the same public client. Stop the backend
to exercise the safe network error and retry flow. Refresh the page to start a new in-memory
conversation.

For the normal database-backed backend, start dependencies with `docker compose up -d`. Backend
startup applies the repository's schema bootstrap and creates the active, public `redmoor` assistant
idempotently. Indexed knowledge must also exist for that assistant; use the repository's established
ingestion workflow rather than editing database rows. The public route remains disabled unless
`PUBLIC_ASSISTANT_CHAT_ENABLED=true`.

The demo origin is `http://localhost:5173`. The backend development default and
`apps/backend/.env.example` already include that exact origin in `PUBLIC_CHAT_ALLOWED_ORIGINS`; keep
it when overriding the comma-separated list. Do not use a wildcard origin or browser `no-cors` mode.

Troubleshooting:

- A configuration page names missing or invalid frontend variables; update `apps/assistant-demo/.env`
  and restart Vite.
- A browser CORS error means the exact frontend origin is absent from
  `PUBLIC_CHAT_ALLOWED_ORIGINS` or the backend was not restarted after it changed.
- “Currently unavailable” during bootstrap means the slug was not found, is inactive/private, or
  has no valid published configuration. Confirm `VITE_ASSISTANT_ID=redmoor` and the backend gate.
- A configuration network error usually means the backend is not running at
  `VITE_ASSISTANT_API_BASE_URL`; start it and reload the page. Chat network errors retain the
  widget's retry button.
- A safe generic server error hides provider and backend details by design; inspect backend logs for
  configuration or provider failures without logging conversation content.
