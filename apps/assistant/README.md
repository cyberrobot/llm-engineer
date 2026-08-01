# Assistant widget

`@ai-discovery-assistant/assistant` contains the inline React assistant UI and the existing
typed API client. The widget owns a bounded in-memory conversation and request lifecycle when an
`AssistantChatClient` is supplied. PR 12B intentionally keeps that client contract independent of
the future public HTTP schema; PR 12C will provide the real API adapter after the backend contract
lands.

## Run the demo

From the repository root:

```sh
npm install
npm run dev --workspace @ai-discovery-assistant/assistant
```

The Vite page includes mock multi-turn, pending, retryable failure, unavailable-assistant,
long-content, and 320px container examples. Mock behavior lives only under `src/demo`; it is not
exported from the package entry point and makes no network requests.

## Embed the widget

```tsx
import {
  AssistantWidget,
  type AssistantChatClient,
} from '@ai-discovery-assistant/assistant'

const chatClient: AssistantChatClient = {
  historyLimit: 10,
  async send(request, { signal }) {
    return testOrHostAdapter.send(request, { signal })
  },
}

export function ContactPage() {
  return (
    <section aria-labelledby="assistant-heading">
      <h2 id="assistant-heading">Ask Redmoor</h2>
      <AssistantWidget
        assistantName="Redmoor Assistant"
        welcomeMessage="How can I help?"
        suggestedQuestions={[
          'What services do you offer?',
          'Can you help us build an AI assistant?',
        ]}
        chatClient={chatClient}
      />
    </section>
  )
}
```

## Public props

| Prop | Type | Behaviour |
| --- | --- | --- |
| `assistantName` | `string` | Visible name and accessible conversation/input labels. Defaults to `Assistant`. |
| `welcomeMessage` | `string` | Initial assistant text in uncontrolled mode. |
| `placeholder` | `string` | Composer placeholder text. |
| `suggestedQuestions` | `readonly string[]` | Optional buttons shown until the conversation starts. Selecting one submits it. |
| `messages` | `readonly AssistantMessage[]` | Enables controlled rendering. The host owns all message ordering and updates. |
| `chatClient` | `AssistantChatClient` | Enables local conversation state through an injected, abortable client. The client supplies its history limit. |
| `onSubmit` | `(message: string) => void \| Promise<void>` | Receives trimmed, non-empty text. A returned promise controls the pending state. |
| `onError` | `(error: unknown) => void` | Optional host error hook. Raw errors are never rendered or logged by the widget. |

`AssistantMessage` contains only `id`, `role` (`user` or `assistant`), and plain-text `content`.
Content is rendered as React text, without Markdown or HTML interpretation.

## State and integration boundary

With `chatClient` and without `messages`, the widget appends questions immediately, sends only
completed conversational history, renders answers, exposes safe failure states, and supports
manual retry without duplicating the question. Requests are single-flight and aborted on unmount
or when the configured client changes. Conversation state is reset with the client and is never
persisted.

The existing `messages`/`onSubmit` controlled integration remains supported for backward
compatibility. When `messages` is supplied, the host continues to own ordering and updates.

`AssistantChatClient` is a frontend port, not the PR 11C HTTP contract. It accepts a question,
bounded prior messages, and an `AbortSignal`, and returns one plain-text answer. Implementations map
their failures to `AssistantChatError` without exposing provider details. The widget has no direct
fetch calls, retrieval, citations, authentication, Markdown, storage, analytics, or streaming.
