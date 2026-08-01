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
published tarball. Publication and release automation are intentionally handled separately.
