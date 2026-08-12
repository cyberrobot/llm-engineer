export interface AssistantWidgetMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantWidgetProps {
  /** Public assistant slug used by the backend route. */
  assistantId: string
  /** Public API origin or base path, without the assistant endpoint. */
  apiBaseUrl: string
  assistantName?: string
  welcomeMessage?: string
  placeholder?: string
  suggestedQuestions?: readonly string[]
}
