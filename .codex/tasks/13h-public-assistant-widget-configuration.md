PR 13H — Propagate Published Assistant Configuration to Public Widget

Repository state

Expected branch:

feature/13h-public-assistant-widget-configuration

Base branch:

main

Worktree:

Use a fresh worktree or branch based on current origin/main.

Dependencies:

- PR 11G — Assistant Behaviour, Publishing & Preview backend contract
- PR 13D — Assistant Behaviour, Prompts, Publishing & Preview Admin UI
- Existing public Assistant chat contract
- Existing @redmoor/assistant-widget package
- Existing Assistant lifecycle contract requiring status=active and visibility=public for public access

The current repository already persists and revisions these Assistant behaviour fields:

- instructions
- welcome_message
- input_placeholder
- suggested_questions

Public chat already resolves the published behaviour revision for generation.

However, the public widget currently accepts presentation configuration directly from the embedding host:

interface AssistantWidgetProps {
assistantId: string
apiBaseUrl: string
assistantName?: string
welcomeMessage?: string
placeholder?: string
suggestedQuestions?: readonly string[]
}

AssistantWidget passes those values directly into the conversation component.

The widget backend client currently calls only:

POST /public/assistants/{assistantId}/chat

There is no public Assistant bootstrap/configuration request.

As a result, publishing Admin-managed presentation behaviour does not propagate to existing widget installations unless each host application separately updates its hard-coded props.

This PR closes that integration gap.

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- packages/assistant-widget/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/TEMPLATE.md
- .codex/tasks/11g-assistant-behaviour-publishing-preview.md
- .codex/tasks/13d-assistant-behaviour-publishing-preview.md
- apps/backend/docs/assistant-behaviour.md
- relevant Assistant domain and repository code
- relevant public Assistant chat API code
- apps/backend/tests/test_public_chat.py
- packages/assistant-widget/src/index.ts
- packages/assistant-widget/src/AssistantWidget.tsx
- packages/assistant-widget/src/AssistantWidget.types.ts
- packages/assistant-widget/src/publicChatClient.ts
- packages/assistant-widget/src/components/assistant-widget/
- packages/assistant-widget/README.md
- apps/assistant-demo/src/
- apps/assistant-demo/package.json

Primary change area

Expected primary change surface:

apps/backend/assistant/api/
apps/backend/assistant/application/
apps/backend/assistant/schemas/
apps/backend/tests/
packages/assistant-widget/src/
packages/assistant-widget/README.md
apps/assistant-demo/src/

Only modify dependency-injection/router/bootstrap files where required to expose the new public contract.

Canonical implementation examples

Backend:

- existing public Assistant availability semantics from public chat;
- existing published behaviour resolution used by public chat;
- apps/backend/docs/assistant-behaviour.md;
- existing public API error mapping and OpenAPI tests.

Widget:

- packages/assistant-widget/src/publicChatClient.ts for public transport conventions;
- packages/assistant-widget/src/AssistantWidget.tsx for the package facade;
- existing rendered loading/error behaviour and component-testing conventions.

Reuse the same Assistant availability rules and published-behaviour source used by public chat rather than implementing a parallel interpretation.

Relevant symbols

Verify exact current names before implementation.

Expected relevant symbols include:

- AssistantWidget
- AssistantWidgetProps
- createPublicChatClient
- AssistantWidgetConversation
- public Assistant chat service/repository
- AssistantBehaviourState
- published Assistant behaviour revision
- Assistant lifecycle/status/visibility models
- AssistantNotFound

Expected change surface

Expected additions or changes include:

1. A safe unauthenticated public Assistant configuration/bootstrap endpoint.
2. Backend response schema exposing published presentation configuration only.
3. A widget configuration client.
4. Widget bootstrap/loading/error behaviour.
5. Resolution rules between server configuration and optional explicit widget props.
6. Demo integration updated to use server-managed defaults.
7. Backend and widget tests.
8. Public widget/backend documentation.
9. A Changeset if required by the repository’s package-release policy because the public widget package behaviour changes.

Excluded areas

Do not modify unless directly required by an existing contract:

- Admin behaviour editing UI;
- Admin publishing workflow;
- behaviour revision persistence model;
- migrations;
- retrieval;
- embeddings;
- ingestion;
- evaluation;
- operations/admin APIs;
- model/provider configuration;
- generation parameters;
- public chat SSE protocol;
- widget release workflow itself;
- widget visual redesign;
- branding/theme system;
- analytics;
- conversation persistence;
- arbitrary public access to draft configuration.

Do not expose instructions through the public configuration endpoint.

Do not expose:

- draft behaviour;
- concurrency tokens;
- administrator IDs;
- internal Assistant UUIDs unless already intentionally public;
- prompt/system instructions;
- unpublished revisions;
- internal lifecycle metadata not needed by the widget;
- provider configuration;
- retrieval configuration;
- knowledge-source configuration.

⸻

Objective

Make published Assistant presentation configuration authoritative for the public Assistant widget.

After this PR, the normal integration should require only:

<AssistantWidget
  assistantId="redmoor"
  apiBaseUrl="https://api.example.com"
/>

The widget must obtain its default user-facing Assistant presentation from the backend’s currently published configuration.

When an administrator changes and publishes:

- Assistant name, where the canonical public Assistant identity exposes it;
- welcome message;
- input placeholder;
- suggested questions;

an existing widget integration must display the newly published values without requiring a redeployment of the embedding host merely to duplicate that configuration.

Unpublished draft changes must never affect the public widget.

The backend remains the source of truth.

Explicit widget presentation props may remain as optional overrides for deliberate white-label or embedding-specific use cases, but they must no longer be required to reproduce the published Assistant configuration.

⸻

Current architecture

Assistant behaviour is persisted as immutable revisions.

Each Assistant has:

- one current draft revision;
- zero or one published revision.

The published revision contains:

- instructions;
- welcome_message;
- input_placeholder;
- ordered suggested_questions.

Public chat already resolves the published revision and uses its published instructions for generation.

The public Assistant availability boundary independently requires the Assistant to be:

status = active
visibility = public

Saving a draft does not publish it.

Publishing does not activate an Assistant.

Activating an Assistant does not publish a newer draft.

These distinctions must remain unchanged.

The public widget currently has a split source of truth:

Backend published behaviour
│
├── instructions ──────────> public chat generation
│
└── presentation fields ─X─> widget
Embedding host
│
├── welcomeMessage
├── placeholder
├── suggestedQuestions
└── assistantName
│
▼
AssistantWidgetConversation

This means the Admin publishing workflow is only partially propagated to the consumer experience.

For example:

1. Administrator changes welcome_message.
2. Administrator saves the draft.
3. Administrator publishes it.
4. Public generation starts using the published revision.
5. Existing embedded widgets continue displaying their old host-supplied welcome message.

That behaviour is incorrect for an Admin-managed Assistant platform.

The target architecture is:

Published Assistant revision
│
▼
Public Assistant bootstrap API
│
▼
@redmoor/assistant-widget
│
▼
AssistantWidgetConversation

Public chat and public presentation must therefore resolve from the same published Assistant state.

⸻

Required implementation

1. Add an authoritative public Assistant bootstrap/configuration contract

Add a public read endpoint conceptually equivalent to:

GET /public/assistants/{assistant_slug}

Use the repository’s existing public Assistant slug conventions.

Do not introduce a competing identifier format.

The response should expose only safe information required to render the public widget.

Expected response shape:

{
"id": "redmoor",
"name": "Redmoor Assistant",
"welcome_message": "How can I help?",
"input_placeholder": "Ask a question",
"suggested_questions": [
"What services do you provide?"
],
"published_revision": 3
}

Verify exact field naming against existing backend conventions.

id may instead be named slug if that better matches the existing public API model.

The endpoint must not expose instructions.

The endpoint must return data from the published behaviour revision, never from the current draft.

published_revision should identify the public presentation revision currently being returned and may later support diagnostics/cache invalidation.

Do not expose publication concurrency tokens.

⸻

2. Reuse public Assistant availability semantics

The new endpoint must have the same public visibility boundary as public chat.

An Assistant is publicly discoverable through this endpoint only when it satisfies the existing public availability rules.

Currently those rules require:

status = active
AND
visibility = public

Missing, inactive, private, and otherwise unavailable Assistants must produce equivalent safe not-found behaviour.

Do not leak whether an Assistant exists but is private or inactive.

For example:

GET /public/assistants/private-assistant

must not reveal:

Assistant exists but is private

It should return the same externally observable not-found contract used for missing public Assistants.

Reuse the existing public Assistant eligibility rule rather than duplicating it.

⸻

3. Resolve only the published behaviour revision

The bootstrap response must resolve exactly one published behaviour revision.

It must return:

- welcome_message;
- input_placeholder;
- suggested_questions;

from that published revision.

If Assistant name is part of the Assistant identity rather than behaviour revision, return the currently public Assistant name from the existing Assistant entity.

The endpoint must never return a newer saved draft merely because one exists.

Required scenario:

Published revision: 2
Draft revision: 3

The public endpoint must return revision 2 presentation data.

After revision 3 is published, a subsequent request must return revision 3.

Do not mutate state during this GET request.

⸻

4. Keep instructions private

instructions are server-side generation configuration.

They must never be serialized into the public Assistant bootstrap response.

Add explicit regression coverage proving that the public response contains no:

- instructions;
- system prompt;
- internal prompt representation;
- draft content.

Do not reuse an administrator behaviour response schema and merely omit fields accidentally during serialization.

Create a deliberately narrow public response model.

⸻

5. Define missing-publication behaviour safely

Inspect current domain invariants before implementing this case.

The repository documentation states that existing Assistants and newly created Assistants receive a deterministic published default revision.

If repository inspection confirms every valid public Assistant must therefore have a published revision, preserve that invariant.

If a public Assistant can nevertheless exist without a published revision because of legacy or corrupted state, fail closed.

Do not return draft configuration as a fallback.

Do not silently construct host/default presentation configuration that could make an unpublished draft appear public.

Use a stable safe unavailable/not-found response consistent with the public Assistant contract.

⸻

6. Keep the endpoint unauthenticated

The bootstrap endpoint is part of the anonymous public Assistant boundary.

It must not require:

- administrator authentication;
- administrator cookies;
- trusted administrator origin validation.

It must remain constrained by the same public exposure rules as public chat.

Do not weaken administrator APIs to implement this endpoint.

Do not call administrator endpoints from the widget.

⸻

7. Preserve CORS/public browser compatibility

The public widget runs inside third-party websites.

The bootstrap endpoint must be usable from the same browser origins supported by public chat.

Follow the existing public API CORS policy.

Do not introduce credentialed cross-origin requests.

The widget configuration request must not send administrator cookies or credentials.

If existing middleware already covers the route correctly, reuse it rather than adding endpoint-specific CORS logic.

⸻

8. Add a public Assistant configuration client to the widget

Add a small transport boundary for loading public Assistant configuration.

A suitable API may be conceptually:

createPublicAssistantClient(...)

or:

getPublicAssistantConfiguration(...)

Choose naming consistent with the existing package.

The client should request:

GET {apiBaseUrl}/public/assistants/{assistantId}

The React component itself must not call fetch() directly.

Maintain the architecture:

AssistantWidget
↓
public configuration client
↓
backend

and separately:

AssistantWidgetConversation
↓
chat client
↓
backend

A combined public Assistant client is acceptable if it materially simplifies the contract without creating unnecessary abstraction.

⸻

9. Validate the public configuration response

Do not blindly trust successful JSON.

Validate the required response shape before passing it into the conversation component.

At minimum validate:

- Assistant identifier/slug;
- name where required;
- welcome message type;
- input placeholder type;
- suggested questions as an ordered string array;
- published revision type/range.

Malformed successful responses must result in a safe widget configuration error.

Do not render arbitrary malformed values.

Do not add a large schema-validation dependency solely for this contract if the existing package does not already use one and a small explicit validator is sufficient.

⸻

10. Bootstrap configuration before rendering authoritative presentation

AssistantWidget must load the public Assistant configuration for its assistantId and apiBaseUrl.

The server response becomes the default source for:

assistantName
welcomeMessage
placeholder
suggestedQuestions

The conversation component should receive the resolved values.

The widget must not initially render stale built-in or host defaults as though they were authoritative and then silently replace them in a visually confusing way.

Provide a bounded initial loading state appropriate for an inline widget.

Do not redesign the widget.

⸻

11. Define explicit override precedence

Retain existing presentation props only if they have a deliberate compatibility or white-label purpose.

If retained, define precedence explicitly as:

explicit prop
↓
published server configuration

For example:

resolvedWelcomeMessage =
welcomeMessage !== undefined
? welcomeMessage
: publicConfig.welcome_message

Use undefined as the signal for “no override”.

Do not use truthiness.

This matters because an explicitly supplied empty string may be meaningful, particularly for the welcome message.

The same principle applies to arrays.

An explicitly supplied:

suggestedQuestions={[]}

must remain capable of intentionally hiding server-managed suggestions if explicit overrides continue to be supported.

Document this behaviour clearly.

Do not require host overrides for normal operation.

⸻

12. Preserve backward compatibility deliberately

Existing integrations may currently provide:

<AssistantWidget
  assistantId="redmoor"
  apiBaseUrl="https://api.example.com"
  assistantName="Redmoor"
  welcomeMessage="..."
  placeholder="..."
  suggestedQuestions={[...]}
 />

Do not unnecessarily break these consumers.

Prefer maintaining those optional props as explicit overrides.

However, the component must still fetch authoritative public configuration unless repository inspection identifies a strong reason not to.

The host must not become responsible for supplying server-managed defaults.

If an optimisation is introduced to skip configuration loading when every presentation field is explicitly overridden, do not implement it unless it is clearly necessary and does not undermine:

- Assistant availability checks;
- published revision awareness;
- predictable integration semantics.

The simplest correct implementation is preferred.

⸻

13. Define configuration-loading states

The widget must distinguish at least:

- configuration loading;
- configuration loaded;
- Assistant unavailable;
- configuration network failure;
- malformed successful response.

Do not collapse all failures into an unhelpful blank widget.

Use safe user-facing text consistent with the widget’s existing error language.

Do not expose:

- stack traces;
- raw response bodies;
- internal backend messages;
- unpublished configuration.

A failed bootstrap request must not silently fall back to potentially stale host defaults and create the impression that the Assistant is correctly configured.

Explicit overrides are presentation overrides, not permission to bypass public Assistant availability.

⸻

14. Do not weaken chat availability

The existing chat endpoint remains authoritative for chat requests.

Loading the bootstrap successfully must not be treated as permanent proof that the Assistant remains available.

For example:

1. Widget loads configuration.
2. Assistant is later made private.
3. User sends a message.
4. Existing public chat request returns unavailable.

The widget must continue handling that using the existing chat error behaviour.

Do not cache authorization/availability indefinitely in client state.

⸻

15. Handle publication changes correctly

A newly mounted widget must retrieve the latest published revision.

Required lifecycle:

Admin saves draft revision 4
│
└── existing public config remains revision 3
Admin publishes revision 4
│
▼
next bootstrap request returns revision 4

Do not expose saved draft changes before publication.

For an already-mounted widget, automatic live synchronization is not required by this PR unless the existing application has a refresh/revalidation abstraction that makes it trivial.

Do not introduce:

- polling;
- WebSockets;
- server-sent configuration updates;

solely for this requirement.

A page reload/remount obtaining the newly published configuration is sufficient.

⸻

16. Avoid unsafe long-lived caching

Because publication is intended to propagate without host redeployment, ensure caching does not cause the old published presentation to persist unexpectedly.

Inspect existing API caching policy.

For this PR, prefer a conservative response policy unless the project already has a revision-aware cache strategy.

Do not introduce long immutable browser caching for:

GET /public/assistants/{slug}

If response caching is used, document how publication becomes visible and ensure stale configuration cannot persist beyond an intentional bounded period.

Do not add cache invalidation infrastructure unless repository architecture already provides it and it is required.

⸻

17. Update the Assistant demo to exercise the standard integration

Update apps/assistant-demo so the normal demonstration uses backend-managed configuration rather than duplicating Admin-managed presentation text.

The primary usage should be conceptually:

<AssistantWidget
  assistantId={assistantId}
  apiBaseUrl={apiBaseUrl}
/>

Keep explicit override examples only when they demonstrate supported white-label behaviour intentionally.

The demo should therefore prove that the published backend configuration is sufficient to render the widget.

Do not hard-code production behaviour values into the demo as the normal integration path.

⸻

18. Update public package documentation

Update packages/assistant-widget/README.md.

Document:

- minimum integration;
- backend bootstrap request;
- server-managed presentation defaults;
- publication semantics;
- explicit prop override semantics;
- distinction between assistantId and backend Assistant UUID if relevant;
- behaviour when Assistant is inactive/private/unavailable;
- configuration-load failure behaviour.

Primary example:

import { AssistantWidget } from '@redmoor/assistant-widget'
import '@redmoor/assistant-widget/styles.css'
<AssistantWidget
  assistantId="redmoor"
  apiBaseUrl="https://api.example.com"
/>

Explain that published Assistant configuration supplies the default:

- Assistant name;
- welcome message;
- input placeholder;
- suggested questions.

Do not document unpublished behaviour as publicly visible.

⸻

19. Update backend documentation

Extend the relevant public Assistant/backend documentation to describe:

GET /public/assistants/{assistant_slug}

Document:

- anonymous access;
- lifecycle availability rules;
- published-only behaviour resolution;
- response fields;
- deliberate exclusion of instructions;
- safe not-found semantics;
- caching semantics if applicable.

Keep apps/backend/docs/assistant-behaviour.md aligned with the implementation.

⸻

20. Package release compatibility

This PR changes externally observable behaviour of @redmoor/assistant-widget.

Inspect the repository’s current Changesets policy.

If a changeset is required for qualifying package source changes, add the appropriate changeset.

This should normally be treated as a backward-compatible feature addition rather than a breaking API change if the existing optional presentation props remain supported.

Do not manually increment packages/assistant-widget/package.json when the repository’s Changesets workflow owns versioning.

⸻

21. No duplicate publication model

Do not introduce a second widget-specific configuration store.

Do not persist presentation configuration in:

- local storage;
- session storage;
- the demo;
- widget-specific backend tables;
- environment variables as the authoritative source.

The existing Assistant behaviour publication model remains authoritative.

The intended relationship is:

Admin draft
│
│ publish
▼
Published Assistant behaviour revision
│
├── instructions ─────> server-side generation only
│
└── presentation ─────> public bootstrap endpoint
│
▼
AssistantWidget

⸻

Acceptance criteria

- A public unauthenticated Assistant bootstrap/configuration endpoint exists using the established public Assistant slug.
- The endpoint returns the currently published Assistant presentation configuration.
- The endpoint returns the Assistant’s public name where required by the widget contract.
- The endpoint returns welcome_message.
- The endpoint returns input_placeholder.
- The endpoint returns ordered suggested_questions.
- The endpoint returns published_revision.
- The endpoint never returns Assistant instructions.
- The endpoint never returns draft configuration.
- The endpoint never returns administrator concurrency tokens.
- Missing, inactive, and private Assistants are indistinguishable through the public endpoint.
- Public availability rules are reused rather than reimplemented inconsistently.
- The endpoint does not require administrator authentication.
- The endpoint does not require trusted administrator origin validation.
- Public browser CORS behaviour remains compatible with the existing widget deployment model.
- The endpoint does not mutate Assistant or behaviour state.
- Saving a newer draft does not change public bootstrap output.
- Publishing that newer draft causes a subsequent bootstrap request to return the newly published presentation values.
- AssistantWidget loads public Assistant configuration using assistantId and apiBaseUrl.
- React presentation components do not call fetch() directly.
- Successful configuration responses are validated before rendering.
- Malformed successful responses produce a safe configuration error.
- The normal widget integration requires only assistantId and apiBaseUrl.
- Server-published configuration supplies default Assistant name, welcome message, placeholder, and suggested questions.
- Existing optional presentation props remain supported as explicit overrides unless repository inspection proves a breaking change is required.
- Explicit override precedence is documented and tested.
- Override detection uses undefined, not truthiness.
- An explicit empty welcome message remains distinguishable from no override.
- An explicit empty suggested-question array remains distinguishable from no override.
- Explicit overrides do not allow an unavailable/private Assistant to bypass backend availability rules.
- Configuration loading has a user-visible bounded loading state.
- Missing/unavailable Assistant configuration has a safe user-facing state.
- Network failure has a safe user-facing state.
- Bootstrap failure does not silently render stale host configuration as though it were authoritative.
- Existing public chat behaviour and SSE protocol remain unchanged.
- Existing public chat unavailable/error handling continues to work after configuration has loaded.
- No polling or real-time configuration synchronization is introduced.
- Reloading/remounting after publication obtains the newly published revision.
- The Assistant demo demonstrates the server-managed minimum integration.
- Widget README documents the new standard integration and override semantics.
- Backend documentation describes the public bootstrap contract and published-only semantics.
- OpenAPI documents the public configuration endpoint and its response/error contract.
- Relevant Changeset is added if required by repository release policy.
- No database migration is introduced unless repository inspection identifies an actual persistence gap.
- No duplicate widget-specific configuration persistence is introduced.
- All targeted backend tests pass.
- All Assistant widget tests pass.
- Widget type checking passes.
- Widget lint passes.
- Widget production build passes.
- Assistant demo tests/type checking/lint/build pass where affected.
- Relevant broader repository verification passes.

Tests to add or update

Backend tests should cover the public endpoint through its HTTP boundary.

Expected locations include:

apps/backend/tests/test_public_chat.py

or a focused new public Assistant configuration test module if that creates a clearer boundary.

Add coverage for:

Public configuration — successful response

Given an active/public Assistant with a published behaviour revision:

- GET succeeds;
- response contains public slug/identifier;
- response contains name;
- response contains published welcome message;
- response contains published input placeholder;
- response preserves suggested-question ordering;
- response contains published revision.

Draft isolation

Given:

published revision = 2
draft revision = 3

assert that GET returns revision 2 values.

After publishing revision 3, assert a new GET returns revision 3 values.

Sensitive-field exclusion

Assert the serialized public response does not contain:

- instructions;
- draft prompt content;
- concurrency token;
- administrator-only behaviour metadata.

Public availability

Test equivalent safe responses for:

- missing Assistant;
- inactive/public Assistant;
- active/private Assistant;
- inactive/private Assistant.

The externally observable response must not reveal which unavailable lifecycle state applies.

Missing publication

If repository invariants permit constructing this state, verify the endpoint fails closed and never falls back to draft configuration.

OpenAPI

Verify:

- endpoint exists;
- operation requires no authentication;
- success response model is documented;
- expected errors are documented.

CORS

Where public chat already has route-level CORS coverage, add equivalent coverage proving the configuration endpoint supports intended public browser origins without credentialed administrator access.

⸻

Widget tests should cover the exported AssistantWidget behaviour through the rendered public interface.

Expected locations:

packages/assistant-widget/src/AssistantWidget.test.tsx
packages/assistant-widget/src/publicAssistantClient.test.ts

Use existing naming/layout if different.

Use MSW for rendered HTTP behaviour where practical and existing test conventions support it.

Add coverage for:

Published defaults

Server returns:

{
"id": "redmoor",
"name": "Redmoor",
"welcome_message": "Welcome from server",
"input_placeholder": "Ask Redmoor",
"suggested_questions": ["Question one", "Question two"],
"published_revision": 7
}

Render:

<AssistantWidget
  assistantId="redmoor"
  apiBaseUrl="https://example.test"
/>

Assert the user sees the server-managed presentation.

Bootstrap request

Verify the package requests the correct encoded public Assistant URL using GET.

Test base URLs with and without trailing slash according to existing client conventions.

Loading

Verify a delayed configuration request produces the intended loading state rather than stale conversation content.

Unavailable Assistant

404 must produce the safe unavailable state.

Network failure

Network failure must produce a safe configuration error.

Malformed successful response

Invalid response fields must not be rendered.

Explicit overrides

For each retained optional presentation prop, verify:

explicit prop > published server value

Cover:

- assistantName;
- welcomeMessage;
- placeholder;
- suggestedQuestions.

Also verify:

welcomeMessage=""

does not fall back to the server value.

Verify:

suggestedQuestions={[]}

does not fall back to the server list.

Chat still uses existing client

After configuration loads, sending a question must still use:

POST /public/assistants/{assistantId}/chat

and preserve the existing streaming behaviour.

Availability is not bypassed

If bootstrap succeeds but chat later returns unavailable, verify the widget surfaces the existing chat unavailable state.

Unmount/cancellation

If the current codebase has an established cancellation pattern, verify an in-flight bootstrap does not update unmounted component state.

Do not add arbitrary delays to tests.

⸻

Update Assistant demo tests if they currently assert host-supplied configuration.

The demo’s standard scenario should verify it renders from backend-provided published configuration.

Verification commands

Run from the repository root unless otherwise stated.

# Backend targeted tests

cd apps/backend
pytest tests/test_public_chat.py
cd ../..

# If a dedicated public configuration test module is added:

cd apps/backend
pytest tests/test_public_assistant_config.py
cd ../..

# Backend broader affected suite

npm run test:api

# Assistant widget

npm test --workspace @redmoor/assistant-widget
npm run lint --workspace @redmoor/assistant-widget
npm run typecheck --workspace @redmoor/assistant-widget
npm run build --workspace @redmoor/assistant-widget
npm run pack:check --workspace @redmoor/assistant-widget

# Assistant demo, because the integration contract changes

npm run test --workspace @ai-discovery-assistant/assistant-demo
npm run lint --workspace @ai-discovery-assistant/assistant-demo
npm run typecheck --workspace @ai-discovery-assistant/assistant-demo
npm run build --workspace @ai-discovery-assistant/assistant-demo

# Relevant workspace regression suite

npm test

If backend formatting/type/lint commands are defined elsewhere in the repository or CI, run the repository-standard equivalents for the changed backend files as well.

Do not claim completion if a relevant command fails.

If a command cannot be executed in the development environment, report:

- the exact command;
- the exact reason;
- the observed error;
- the remaining verification risk.
