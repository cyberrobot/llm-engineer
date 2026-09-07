# Repository Map

This document identifies the paths to inspect first. `AGENTS.md` remains the authoritative source
for engineering rules; see `dependency-rules.md` when a change affects architecture boundaries.

## Repository root

- `AGENTS.md` — repository-wide engineering, testing, verification, and Git workflow rules.
- `README.md` — local setup, supported services, and common commands.
- `package.json` — npm workspace membership and repository-level scripts.
- `package-lock.json` — locked JavaScript dependency graph; update it through npm rather than by
  hand.
- `compose.yaml` — local PostgreSQL/pgvector and Redis services.
- `.codex/tasks/TEMPLATE.md` — template for scoped implementation tasks.

The npm workspaces are `apps/*` and `packages/*`. Run workspace commands from the repository root
unless an application document says otherwise.

## Applications

### `apps/backend`

FastAPI backend, ingestion worker, and maintenance tooling. The canonical ASGI entry point is
`apps/backend/main.py` (`main:app`).

Inspect these paths first:

- `apps/backend/api/` — shared API router, health routes, and OpenAPI configuration.
- `apps/backend/assistant/domain/` — assistant, document, ingestion, citation, and evaluation
  business models and rules.
- `apps/backend/assistant/application/` — assistant use-case orchestration; provider-facing
  contracts live in `application/ports/`.
- `apps/backend/assistant/api/` — assistant HTTP routes, request dependencies, and transport
  mapping.
- `apps/backend/assistant/schemas/` — assistant request and response schemas.
- `apps/backend/assistant/infrastructure/` — repositories, vector stores, ingestion adapters, and
  other assistant-specific integrations.
- `apps/backend/assistant/workers/` and `apps/backend/assistant/maintenance/` — background ingestion
  execution and operational maintenance entry points.
- `apps/backend/admin_auth/` — administrator authentication domain, service, persistence, and HTTP
  boundary.
- `apps/backend/operations/` — operational health domain, application, API, and infrastructure
  layers.
- `apps/backend/infrastructure/` — shared AI, cache, database connection, and schema migration
  adapters.
- `apps/backend/core/` — configuration, authentication, logging, metrics, correlation, and common
  application concerns.
- `apps/backend/shared/` — deliberately shared dependencies, schemas, and utilities.
- `apps/backend/prompts/` — version-controlled model prompts.
- `apps/backend/tests/` — backend behavioural and integration tests.
- `apps/backend/docs/` — backend API and operations runbooks.
- `apps/backend/README.md`, `apps/backend/.env.example`, and `apps/backend/pyproject.toml` — backend
  behaviour, configuration, and Python tool settings.

### `apps/rag-backend`

Staged standalone FastAPI RAG extraction. It owns only the RAG health, chat, and audit routes and
is intentionally not production-routed yet. Its local configuration, provider, Redis, PostgreSQL,
prompt, and lifecycle code must remain independent from `apps/backend` until a later cutover.

Backend dependency rules:

- Domain modules own business rules and remain independent of FastAPI, database sessions,
  provider clients, configuration, and application startup.
- Application modules orchestrate domain behaviour and depend on application-owned ports instead
  of concrete external providers.
- API modules validate and map HTTP input/output; they call application services rather than
  implementing business or persistence rules.
- Infrastructure modules implement persistence and provider contracts. Database access stays in
  established repositories and migration modules.
- Shared infrastructure belongs under `apps/backend/infrastructure/`; assistant-only adapters
  belong under `apps/backend/assistant/infrastructure/`.
- Register routes and runtime dependencies through the existing routers and dependency factories;
  do not make lower-level modules import `main.py` or other startup entry points.
- Keep schema changes in `apps/backend/infrastructure/database/migrations/`, preserve migration
  ordering and idempotency, and cover them with real persistence tests.

### `apps/rag-ui`

Internal React/Vite RAG application. Its browser entry point is `apps/rag-ui/src/main.tsx`, with
application composition in `apps/rag-ui/src/App.tsx`.

Inspect these paths first:

- `apps/rag-ui/src/components/` — rendered UI and colocated Storybook stories.
- `apps/rag-ui/src/services/` — backend request functions; components should use these boundaries
  rather than calling endpoints directly.
- `apps/rag-ui/src/utils/` and `apps/rag-ui/src/types/` — shared frontend utilities and types.
- `apps/rag-ui/.storybook/` and `apps/rag-ui/vitest.config.ts` — Storybook and browser-test setup.
- `apps/rag-ui/vite.config.ts` and `apps/rag-ui/eslint.config.js` — build and lint configuration.

Keep user-visible behaviour covered through rendered interactions and accessible selectors. Add or
update stories for meaningful reusable-component states, and keep backend access behind `src/services/`.

### `apps/admin`

Internal React/Vite application for administrator workflows. Navigate from an affected feature/page
to colocated tests, shared components when required, the API/auth boundary when required, and
`src/App.tsx` or `src/routing.ts` only when composition changes. Inspect `e2e/` and Playwright when
browser-visible behaviour materially changes.

- `apps/admin/src/App.tsx` and `src/routing.ts` — route composition and safe return locations.
- `apps/admin/src/features/` — page and feature behaviour.
- `apps/admin/src/components/` — reusable rendered UI.
- `apps/admin/src/api/` and `src/auth/` — backend and administrator-session boundaries.
- colocated `apps/admin/src/**/*.test.ts` and `*.test.tsx` — feature and component tests;
  `apps/admin/src/test/` — shared test setup.
- `apps/admin/e2e/` and `playwright.config.ts` — Playwright browser and visual tests.
- `apps/admin/vitest.config.ts`, `.storybook/`, `vite.config.ts`, `eslint.config.js`, and
  `tsconfig*.json` — test, Storybook, build, lint, and TypeScript configuration.
- `apps/admin/package.json` — workspace commands and dependencies.

Components use the established API/client boundary; backend authentication and authorization remain
authoritative. Test user-visible behaviour through rendered interactions. Inspect shared composition
only when the change crosses that boundary.

### `packages/assistant-widget`

Publishable `@redmoor/assistant-widget` React package. The supported package surface is declared by
`packages/assistant-widget/src/index.ts` and `packages/assistant-widget/package.json`.

Inspect these paths first:

- `packages/assistant-widget/src/AssistantWidget.tsx` and
  `packages/assistant-widget/src/AssistantWidget.types.ts` — public component facade and public
  types.
- `packages/assistant-widget/src/components/assistant-widget/` — widget UI and bounded conversation
  state.
- `packages/assistant-widget/src/publicChatClient.ts` and `packages/assistant-widget/src/api/` —
  public chat transport.
- `packages/assistant-widget/src/config/` — validated browser configuration.
- `packages/assistant-widget/test-fixtures/consumer/` — package-consumer and deep-import verification
  fixture.
- `packages/assistant-widget/scripts/` — package dry-run and export verification.
- `packages/assistant-widget/README.md` — public usage, contract, release workflow, and current
  limitations.

### `apps/assistant-demo`

Private Vite application for exercising the public assistant widget against a backend. Its source
imports `@redmoor/assistant-widget` through the package root; it does not own or publish widget
implementation code.

Inspect these paths first:

- `apps/assistant-demo/src/AssistantWidgetDemo.tsx` — public-package consumer integration.
- `apps/assistant-demo/src/assistantWidgetDemoConfig.ts` — validated public browser configuration.
- `apps/assistant-demo/vite.config.ts` and `apps/assistant-demo/vitest.config.ts` — local mapping of
  the package name to its public source entry for development and tests.

Assistant package rules:

- Treat the `package.json` `exports` map and root `src/index.ts` exports as public contracts.
- Do not expose internal clients, transport errors, state helpers, hooks, or implementation
  components through the package root.
- Keep React and React DOM as peer dependencies and keep package CSS locally scoped.
- The demo consumes the package-level API; it must not become a second implementation of widget
  behaviour.
- Verify distributable changes with the package build, tests, and `pack:verify` consumer checks.

## Cross-application rules

- `apps/rag-ui`, `apps/assistant-demo`, and `packages/assistant-widget` communicate with the backend
  through HTTP contracts; they do not import backend implementation modules.
- The backend owns authentication, authorization, validation, persistence, idempotency, and safe
  provider-error mapping. Frontend visibility or client-side checks are not security boundaries.
- Provider-specific code stays behind backend adapters. Never place credentials, raw provider
  payloads, prompts, document contents, or conversation contents in browser configuration or logs.
- Preserve deterministic ordering, stable serialized values, and existing API/package exports.
- Add behaviour-focused tests beside the affected frontend code or under `apps/backend/tests/` as
  appropriate. Use real application layers and repositories when practical; mock only true external
  boundaries.
- Update the relevant README or backend runbook when changing public APIs, configuration,
  operational behaviour, package exports, persisted formats, or recovery procedures.

## Verification entry points

Use the smallest relevant command first, followed by the broader affected checks:

```sh
# All workspace tests that define a test script
npm test

# Backend
npm run test:api

# RAG UI
npm run lint --workspace @ai-discovery-assistant/rag-ui
npm run build --workspace @ai-discovery-assistant/rag-ui
npm run test:storybook

# Admin
npm run lint --workspace @ai-discovery-assistant/admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm test --workspace @ai-discovery-assistant/admin
npm run build --workspace @ai-discovery-assistant/admin
npm run build-storybook --workspace @ai-discovery-assistant/admin

# Assistant widget
npm run lint --workspace @redmoor/assistant-widget
npm test --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget
```

Also run any narrower test file during development and the repository-defined type, lint, build,
migration, or integration checks affected by the change. Report commands that could not be run and
never treat generated directories such as `node_modules/`, `dist/`, caches, uploads, or evaluation
reports as source paths.
