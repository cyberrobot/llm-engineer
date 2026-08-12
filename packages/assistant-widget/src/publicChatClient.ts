import {
  AssistantChatError,
  type AssistantChatClient,
  type AssistantChatErrorCode,
  type AssistantChatRequest,
  type AssistantChatResponse,
  type AssistantChatStreamOptions,
} from './components/assistant-widget/AssistantWidget.types'
import { consumeAssistantEventStream } from './assistantEventStream'

const PUBLIC_HISTORY_LIMIT = 12

function requestError(status: number): AssistantChatError {
  let code: AssistantChatErrorCode
  let retryable: boolean

  switch (status) {
    case 400:
    case 422:
      code = 'invalid_request'
      retryable = false
      break
    case 404:
    case 503:
      code = 'assistant_unavailable'
      retryable = false
      break
    case 429:
      code = 'rate_limited'
      retryable = true
      break
    default:
      code = 'server_error'
      retryable = status >= 500
  }

  return new AssistantChatError(code, retryable)
}

export function createPublicChatClient(
  apiBaseUrl: string,
  assistantId: string,
  fetchImplementation: typeof globalThis.fetch = globalThis.fetch,
): AssistantChatClient {
  const baseUrl = apiBaseUrl.trim().replace(/\/+$/, '')
  const normalizedAssistantId = assistantId.trim()

  async function requestChat(
    request: AssistantChatRequest,
    options: AssistantChatStreamOptions,
  ): Promise<AssistantChatResponse> {
    if (baseUrl.length === 0 || normalizedAssistantId.length === 0) {
      throw new AssistantChatError('invalid_request', false)
    }

    let response: Response
    try {
      response = await fetchImplementation(
        `${baseUrl}/public/assistants/${encodeURIComponent(normalizedAssistantId)}/chat`,
        {
          method: 'POST',
          headers: {
            Accept: 'text/event-stream',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(request),
          signal: options.signal,
        },
      )
    } catch (error: unknown) {
      if (options.signal.aborted) throw error
      throw new AssistantChatError('network_error', true)
    }

    if (!response.ok) throw requestError(response.status)
    if (!response.headers.get('content-type')?.toLowerCase().includes('text/event-stream')) {
      throw new AssistantChatError('invalid_response', true)
    }

    return consumeAssistantEventStream(response.body, options)
  }

  return {
    historyLimit: PUBLIC_HISTORY_LIMIT,
    async send(request, { signal }) {
      return requestChat(request, { signal, onDelta: () => undefined })
    },
    async stream(request, options) {
      return requestChat(request, options)
    },
  }
}
