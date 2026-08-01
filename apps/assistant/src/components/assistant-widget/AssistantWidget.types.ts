export type AssistantMessageRole = 'user' | 'assistant'

export interface AssistantMessage {
  id: string
  role: AssistantMessageRole
  content: string
}

export type AssistantChatErrorCode =
  | 'assistant_unavailable'
  | 'rate_limited'
  | 'invalid_request'
  | 'network_error'
  | 'server_error'
  | 'invalid_response'

export class AssistantChatError extends Error {
  readonly code: AssistantChatErrorCode
  readonly retryable: boolean

  constructor(code: AssistantChatErrorCode, retryable: boolean) {
    super(code)
    this.name = 'AssistantChatError'
    this.code = code
    this.retryable = retryable
  }
}

export interface AssistantChatRequest {
  message: string
  history: readonly AssistantChatHistoryMessage[]
}

export interface AssistantChatHistoryMessage {
  role: AssistantMessageRole
  content: string
}

export interface AssistantChatResponse {
  answer: string
}

export interface AssistantChatClient {
  readonly historyLimit: number
  send(
    request: AssistantChatRequest,
    options: { signal: AbortSignal },
  ): Promise<AssistantChatResponse>
}

export interface AssistantWidgetProps {
  assistantName?: string
  welcomeMessage?: string
  placeholder?: string
  suggestedQuestions?: readonly string[]
  messages?: readonly AssistantMessage[]
  chatClient?: AssistantChatClient
  onSubmit?: (message: string) => void | Promise<void>
  onError?: (error: unknown) => void
}
