export type AssistantMessageRole = 'user' | 'assistant'

export interface AssistantMessage {
  id: string
  role: AssistantMessageRole
  content: string
}

export interface AssistantWidgetProps {
  assistantName?: string
  welcomeMessage?: string
  placeholder?: string
  suggestedQuestions?: readonly string[]
  messages?: readonly AssistantMessage[]
  onSubmit?: (message: string) => void | Promise<void>
  onError?: (error: unknown) => void
}
