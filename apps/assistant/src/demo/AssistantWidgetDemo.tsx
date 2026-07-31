import { useRef, useState } from 'react'

import { AssistantWidget, type AssistantMessage } from '../components/assistant-widget'

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

const initialInteractiveMessages: readonly AssistantMessage[] = [
  {
    id: 'interactive-welcome',
    role: 'assistant',
    content: 'Hello. Ask me a question about Redmoor Consulting.',
  },
]

export function AssistantWidgetDemo() {
  const nextMessageNumber = useRef(0)
  const [rejectionHandled, setRejectionHandled] = useState(false)
  const [messages, setMessages] = useState<readonly AssistantMessage[]>(
    initialInteractiveMessages,
  )

  async function handleSubmit(content: string) {
    nextMessageNumber.current += 1
    const messageNumber = nextMessageNumber.current
    setMessages((current) => [
      ...current,
      { id: `demo-user-${messageNumber}`, role: 'user', content },
    ])

    await new Promise((resolve) => window.setTimeout(resolve, 1_200))

    setMessages((current) => [
      ...current,
      {
        id: `demo-assistant-${messageNumber}`,
        role: 'assistant',
        content:
          'This is a static demo response for layout review only. A later integration will supply real assistant responses.',
      },
    ])
  }

  return (
    <main className="demoPage">
      <header className="demoIntro">
        <p className="demoEyebrow">Component development</p>
        <h1>Assistant widget foundation</h1>
        <p>
          These examples exercise initial, interactive, filled, long-content, pending, rejected,
          and constrained-width states without making network requests.
        </p>
      </header>

      <section className="demoSection" aria-labelledby="interactive-heading">
        <div className="demoSectionHeading">
          <p>Interactive example</p>
          <h2 id="interactive-heading">Ask Redmoor</h2>
          <span>Submissions remain pending for 1.2 seconds before a static demo reply.</span>
        </div>
        <AssistantWidget
          assistantName="Redmoor Assistant"
          messages={messages}
          onSubmit={handleSubmit}
          placeholder="Ask Redmoor a question…"
          suggestedQuestions={redmoorSuggestions}
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
          <p>Host-handled failure</p>
          <h2 id="rejection-heading">Rejected submission</h2>
          <span>
            Submit a question to verify that the composer is restored and the host error callback
            runs without exposing exception details.
          </span>
          <output className="demoResult" aria-live="polite">
            {rejectionHandled ? 'The host handled the simulated failure.' : ''}
          </output>
        </div>
        <AssistantWidget
          assistantName="Redmoor Assistant"
          onError={() => setRejectionHandled(true)}
          onSubmit={async () => {
            setRejectionHandled(false)
            await new Promise((resolve) => window.setTimeout(resolve, 600))
            throw new Error('Simulated demo submission failure')
          }}
          welcomeMessage="Try a submission that the demo host will reject."
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
