import {
  AssistantWidgetConversation,
  AssistantWidget,
  type AssistantChatClient,
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

const previewClient: AssistantChatClient = {
  historyLimit: 12,
  async send() {
    return { answer: 'The injected client type resolves.' }
  },
}

export function App() {
  return (
    <main>
      <p hidden>{exampleMessage.content}</p>
      <AssistantWidget {...configuration} />
      <AssistantWidgetConversation assistantName="Preview" chatClient={previewClient} />
    </main>
  )
}
