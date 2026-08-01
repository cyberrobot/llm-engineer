import {
  AssistantWidget,
  type AssistantWidgetMessage,
  type AssistantWidgetProps,
} from '@redmoor/assistant-widget'
import '@redmoor/assistant-widget/styles.css'

const configuration: AssistantWidgetProps = {
  assistantId: 'test-assistant',
  apiBaseUrl: 'https://api.example.test',
  welcomeMessage: 'How can I help?',
}

const exampleMessage: AssistantWidgetMessage = {
  id: 'example',
  role: 'assistant',
  content: 'The public message type resolves.',
}

export function App() {
  return (
    <main>
      <p hidden>{exampleMessage.content}</p>
      <AssistantWidget {...configuration} />
    </main>
  )
}
