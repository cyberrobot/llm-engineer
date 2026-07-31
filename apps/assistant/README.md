# Assistant widget

`@ai-discovery-assistant/assistant` contains the inline React assistant UI and the existing
typed API client. The widget is a presentation foundation: it renders conversation content,
collects input, and reports submissions, but it does not call the API or produce assistant
answers.

## Run the demo

From the repository root:

```sh
npm install
npm run dev --workspace @ai-discovery-assistant/assistant
```

The Vite page includes initial, interactive, pending, rejected, multi-message, long-content, and
320px container examples. Demo replies and simulated failures live only under `src/demo`; the demo
is not exported from the package entry point.

## Embed the widget

```tsx
import { AssistantWidget } from '@ai-discovery-assistant/assistant'

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
        onSubmit={async (message) => {
          // Public chat API integration will be added in a later PR.
          await queueMessageForFutureIntegration(message)
        }}
        onError={(error) => reportIntegrationError(error)}
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
| `onSubmit` | `(message: string) => void \| Promise<void>` | Receives trimmed, non-empty text. A returned promise controls the pending state. |
| `onError` | `(error: unknown) => void` | Optional host error hook. Raw errors are never rendered or logged by the widget. |

`AssistantMessage` contains only `id`, `role` (`user` or `assistant`), and plain-text `content`.
Content is rendered as React text, without Markdown or HTML interpretation.

## State and integration boundary

Without `messages`, the widget owns a local display-only list containing the welcome message and
submitted user messages. With `messages`, the host owns the displayed list; the widget still owns
composer and pending UI state but does not append a second user message. This controlled mode is
the seam for the later public chat API integration.

The host remains responsible for API calls, server conversation history, assistant identifiers,
assistant responses, retry/error policy, streaming, persistence, analytics, rate limits, and abuse
protection. This foundation has no retrieval, citations, authentication, Markdown, storage,
network requests, or production conversation state.
