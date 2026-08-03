import { AssistantWidget } from '../index'
import { readAssistantWidgetDemoConfig } from './assistantWidgetDemoConfig'

const redmoorSuggestions = [
  'What services does Redmoor Consulting offer?',
  'Can you help us build an AI assistant?',
  'Do you work with digital agencies?',
] as const

const environmentExample = `VITE_ASSISTANT_API_BASE_URL=http://localhost:8000
VITE_ASSISTANT_ID=redmoor`

export function AssistantWidgetDemo() {
  const result = readAssistantWidgetDemoConfig()

  if (!result.ok) {
    const heading =
      result.reason === 'missing'
        ? 'Assistant demo configuration is incomplete'
        : 'Assistant demo configuration is invalid'

    return (
      <main className="demoPage">
        <header className="demoIntro">
          <p className="demoEyebrow">Connected development demo</p>
          <h1>{heading}</h1>
          <p>
            Check {result.variables.join(' and ')} in the assistant frontend environment, then
            restart the Vite development server.
          </p>
        </header>
        <section className="demoConfigError" aria-labelledby="configuration-heading">
          <h2 id="configuration-heading">Expected .env configuration</h2>
          <pre>{environmentExample}</pre>
          <p>
            The API base URL must be an absolute HTTP or HTTPS URL. The assistant ID must be a
            lowercase route-safe slug.
          </p>
        </section>
      </main>
    )
  }

  const { apiBaseUrl, assistantId } = result.config

  return (
    <main className="demoPage">
      <header className="demoIntro">
        <p className="demoEyebrow">Connected development demo</p>
        <h1>Connected assistant demo</h1>
        <p>
          This page uses the public widget and its real API client. Start the backend before asking
          a question; conversation history remains only in this widget instance.
        </p>
      </header>

      <section className="demoSection" aria-labelledby="interactive-heading">
        <div className="demoSectionHeading">
          <p>Real backend</p>
          <h2 id="interactive-heading">Ask Redmoor</h2>
          <span>
            Requests, pending states, errors, and retries use the production integration path.
          </span>

          <aside className="demoConnection" aria-label="Demo connection">
            <h3>Connection</h3>
            <dl>
              <div>
                <dt>API base URL</dt>
                <dd>
                  <code>{apiBaseUrl}</code>
                </dd>
              </div>
              <div>
                <dt>Assistant ID</dt>
                <dd>
                  <code>{assistantId}</code>
                </dd>
              </div>
            </dl>
            <p>The backend must be running and allow this page&apos;s origin.</p>
          </aside>
        </div>

        <AssistantWidget
          apiBaseUrl={apiBaseUrl}
          assistantId={assistantId}
          assistantName="Redmoor Assistant"
          placeholder="Ask Redmoor a question…"
          suggestedQuestions={redmoorSuggestions}
          welcomeMessage="Hello. Ask me a question about Redmoor Consulting."
        />
      </section>
    </main>
  )
}
