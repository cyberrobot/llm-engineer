import { assistantConfig } from '../config/assistantConfig'
import { HttpClient } from './client'
import type { components, paths } from './types/schema'

type ChatOperation = paths['/assistant/chat']['post']

export type ChatRequest = ChatOperation['requestBody']['content']['application/json']
export type ChatResponse = ChatOperation['responses'][200]['content']['application/json']
type SourceReference = components['schemas']['SourceReference']

export interface AssistantApi {
  chat(request: ChatRequest): Promise<ChatResponse>
}

function isSourceReference(value: unknown): value is SourceReference {
  if (typeof value !== 'object' || value === null) return false

  const source = value as Record<string, unknown>
  return typeof source.id === 'string' && typeof source.title === 'string'
}

function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== 'object' || value === null) return false

  const response = value as Record<string, unknown>
  return (
    typeof response.message === 'string' &&
    Array.isArray(response.sources) &&
    response.sources.every(isSourceReference)
  )
}

export function createAssistantApi(client: HttpClient): AssistantApi {
  return {
    chat(request) {
      return client.post('/assistant/chat', request, isChatResponse)
    },
  }
}

const assistantApi = createAssistantApi(
  new HttpClient({
    baseUrl: assistantConfig.apiBaseUrl,
  }),
)

export function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return assistantApi.chat(request)
}
