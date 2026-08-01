export { createAssistantApi, sendChatMessage } from './api/assistant'
export type { AssistantApi, ChatRequest, ChatResponse } from './api/assistant'
export { AssistantApiError, HttpClient } from './api/client'
export type { ApiErrorCode, ApiLogger, HttpClientOptions } from './api/client'
export { assistantConfig } from './config/assistantConfig'
export { AssistantWidget } from './components/assistant-widget'
export type {
  AssistantChatClient,
  AssistantChatErrorCode,
  AssistantChatHistoryMessage,
  AssistantChatRequest,
  AssistantChatResponse,
  AssistantMessage,
  AssistantMessageRole,
  AssistantWidgetProps,
} from './components/assistant-widget'
export { AssistantChatError, buildConversationHistory } from './components/assistant-widget'
export type { AssistantConfig } from './types/config'
