import {
  AssistantChatError,
  AssistantWidget,
  type AssistantChatClient,
  type AssistantMessage,
} from '../components/assistant-widget'

const redmoorSuggestions = [
  'What services does Redmoor Consulting offer?',
  'Can you help with an AI assistant?',
  'Do you work with digital agencies?',
] as const

const sampleConversation: readonly AssistantMessage[] = [
  {
    id: 'sample-welcome',
    role: 'assistant',
    content: 'How can I help you explore what Redmoor Consulting could do for your organisation?',
  },
  {
    id: 'sample-question',
    role: 'user',
    content: 'Can you help us plan an AI assistant for a specialist consultancy website?',
  },
  {
    id: 'sample-answer',
    role: 'assistant',
    content:
      'Yes. Redmoor can help shape the use case, identify trustworthy content, design the customer journey, and create a practical delivery roadmap. This deliberately long sample also checks that uninterrupted content such as https://example.test/a/very/long/path/that/must/wrap/inside/the/widget cannot force the host page to scroll horizontally.',
  },
]

let shouldFailRetryExample = true

const demoClient: AssistantChatClient = {
  historyLimit: 6,
  async send({ message, history }, { signal }) {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(resolve, 1_200)
      signal.addEventListener('abort', () => {
        window.clearTimeout(timeout)
        reject(new DOMException('Aborted', 'AbortError'))
      }, { once: true })
    })

    const normalized = message.toLowerCase()
    if (normalized.includes('unavailable')) {
      throw new AssistantChatError('assistant_unavailable', false)
    }
    if (normalized.includes('rate limit')) {
      throw new AssistantChatError('rate_limited', true)
    }
    if (normalized.includes('retry') && shouldFailRetryExample) {
      shouldFailRetryExample = false
      throw new AssistantChatError('network_error', true)
    }

    return {
      answer: `Mock answer for turn ${Math.floor(history.length / 2) + 1}. PR 12C will replace this demo boundary with the public API adapter.`,
    }
  },
}

export function AssistantWidgetDemo() {
  return (
    <main className="demoPage">
      <header className="demoIntro">
        <p className="demoEyebrow">Component development</p>
        <h1>Assistant widget conversation states</h1>
        <p>
          These examples exercise mock multi-turn, pending, retry, unavailable, filled,
          long-content, and constrained-width states without making network requests.
        </p>
      </header>

      <section className="demoSection" aria-labelledby="interactive-heading">
        <div className="demoSectionHeading">
          <p>Interactive example</p>
          <h2 id="interactive-heading">Ask Redmoor</h2>
          <span>Submissions remain pending for 1.2 seconds before a mock reply.</span>
        </div>
        <AssistantWidget
          assistantName="Redmoor Assistant"
          chatClient={demoClient}
          placeholder="Ask Redmoor a question…"
          suggestedQuestions={redmoorSuggestions}
          welcomeMessage="Hello. Ask me a question about Redmoor Consulting."
        />
      </section>

      <section className="demoSection" aria-labelledby="initial-heading">
        <div className="demoSectionHeading">
          <p>Initial state</p>
          <h2 id="initial-heading">Welcome and suggestions</h2>
        </div>
        <AssistantWidget
          assistantName="Redmoor Assistant"
          placeholder="Ask Redmoor a question…"
          suggestedQuestions={redmoorSuggestions}
          welcomeMessage="How can I help you today?"
        />
      </section>

      <section className="demoSection" aria-labelledby="filled-heading">
        <div className="demoSectionHeading">
          <p>Content boundaries</p>
          <h2 id="filled-heading">Multiple and long messages</h2>
        </div>
        <AssistantWidget assistantName="Redmoor Assistant" messages={sampleConversation} />
      </section>

      <section className="demoSection" aria-labelledby="rejection-heading">
        <div className="demoSectionHeading">
          <p>Mocked failures</p>
          <h2 id="rejection-heading">Retry and unavailable states</h2>
          <span>
            Ask &quot;retry this&quot; for a one-time retryable failure, &quot;rate limit&quot; for a
            retryable limit, or &quot;unavailable&quot; for a non-retryable failure.
          </span>
        </div>
        <AssistantWidget
          assistantName="Redmoor Assistant"
          chatClient={demoClient}
          welcomeMessage="Try one of the mocked failure phrases above."
        />
      </section>

      <section className="demoSection" aria-labelledby="narrow-heading">
        <div className="demoSectionHeading">
          <p>Responsive example</p>
          <h2 id="narrow-heading">320px parent container</h2>
        </div>
        <div className="demoNarrow">
          <AssistantWidget
            assistantName="Redmoor Assistant"
            suggestedQuestions={redmoorSuggestions}
            welcomeMessage="This widget follows the width of its host container."
          />
        </div>
      </section>
    </main>
  )
}
