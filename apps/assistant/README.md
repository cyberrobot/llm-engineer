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
      assistantName="Redmoor Assistant"
      welcomeMessage="How can I help?"
      suggestedQuestions={[
        'What services do you offer?',
        'Can you help us build an AI assistant?',
      ]}
    />
  )
}
```

The stylesheet is compiled and locally scoped. Consumers do not need Tailwind, PostCSS, CSS
Modules, or other widget-specific styling configuration.

## Props

| Prop | Type | Required | Behavior |
| --- | --- | --- | --- |
| `assistantId` | `string` | Yes | Public assistant slug placed in the API route. |
| `apiBaseUrl` | `string` | Yes | Public API origin or base path. A trailing slash is accepted. |
| `assistantName` | `string` | No | Visible and accessible name. Defaults to `Assistant`. |
| `welcomeMessage` | `string` | No | Initial assistant message. |
| `placeholder` | `string` | No | Composer placeholder. |
| `suggestedQuestions` | `readonly string[]` | No | Suggestions shown until the first question is submitted. |

The root export also provides the `AssistantWidgetProps` and `AssistantWidgetMessage` TypeScript
types. Internal clients, transport errors, reducers, hooks, and UI components are not public API.

## Behavior

Conversations live only in the current widget instance and are never persisted. The widget calls
`POST /public/assistants/{assistantId}/chat` without authentication, sends bounded completed
conversation history, and permits one request at a time. Supported transient failures show a safe
message and a manual retry action; backend response bodies and raw transport errors are not exposed
or logged. Active requests are aborted when the widget unmounts or its API configuration changes.

React and React DOM are peer dependencies. The supported range is React 19, matching the
repository's tested React version. The ESM package can be imported during server rendering;
browser-only APIs are accessed only when a user sends a question.

## Current limitations

The package does not include citations, incremental response rendering, persisted conversations,
conversation restoration, attachments, authentication, analytics, a floating launcher, iframe or
script-tag embedding, arbitrary white-label theming, or framework-specific wrappers.

## Local development

From the repository root:

```sh
npm install
npm run dev:assistant
npm test --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
```

The local Vite demo and package-consumer fixture are development tools and are excluded from the
published tarball.

## Releasing

Package versions are changed manually in `apps/assistant/package.json` and the repository lockfile.
Before the first release, create an npm trusted publisher for `@redmoor/assistant-widget` with the
GitHub repository owner and name, workflow filename `publish-assistant-widget.yml`, and environment
`npm`. Create that GitHub environment as well; configure required reviewers and deployment branch
or tag rules there when release approval is required. The workflow uses npm's public registry and
GitHub OIDC, so it does not require a long-lived npm token. The npm package must permit public
publication for this scoped package.

To release a version:

1. Update the `version` in `apps/assistant/package.json` with `npm version <version> --workspace
   @redmoor/assistant-widget --no-git-tag-version`, review the resulting manifest and lockfile
   changes, and merge them through the normal review process.
2. From the merged commit, run the widget lint, tests, build, and `pack:verify` checks.
3. Create and push an annotated tag matching the package version exactly:

   ```sh
   git tag -a assistant-widget-v0.1.0 -m "Release assistant widget 0.1.0"
   git push origin assistant-widget-v0.1.0
   ```

The tag starts the **Publish assistant widget** workflow. It checks out that exact tag, rejects a
malformed tag or a tag that differs from `apps/assistant/package.json`, repeats all package checks,
and publishes only `@redmoor/assistant-widget` with public access and npm provenance. An existing
tag can also be selected explicitly with the workflow's manual `release_tag` input.

If validation or a package check fails, fix the problem through a reviewed commit, update the
package version when appropriate, and create a new matching tag; do not move a published release
tag. If publication fails before npm accepts the package, re-run the same workflow after correcting
the npm trusted-publisher or GitHub environment configuration. If npm already contains that version,
a retry fails safely because npm versions are immutable: bump the package version and release a new
matching tag instead.

### Connected backend demo

The primary Vite demo is a real consumer of the package-level `AssistantWidget` API. It uses the
same public client as a host application, keeps conversation history in memory, and never stores or
logs questions and answers. Only automated tests intercept HTTP; normal local use requires a running
backend.

Create `apps/assistant/.env` from `apps/assistant/.env.example`:

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

- A configuration page names missing or invalid frontend variables; update `apps/assistant/.env`
  and restart Vite.
- A browser CORS error means the exact frontend origin is absent from
  `PUBLIC_CHAT_ALLOWED_ORIGINS` or the backend was not restarted after it changed.
- “Currently unavailable” means the slug was not found, is inactive/private, or the public route is
  unavailable. Confirm `VITE_ASSISTANT_ID=redmoor` and the backend gate.
- A network error usually means the backend is not running at `VITE_ASSISTANT_API_BASE_URL`; start it
  and use the widget's retry button.
- A safe generic server error hides provider and backend details by design; inspect backend logs for
  configuration or provider failures without logging conversation content.
