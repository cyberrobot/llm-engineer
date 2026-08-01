import {
  AssistantChatError,
  type AssistantChatClient,
  type AssistantChatErrorCode,
} from './components/assistant-widget/AssistantWidget.types'

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

function parseEventStream(value: string): string {
  const answer: string[] = []
  let completed = false

  for (const block of value.replaceAll('\r\n', '\n').split('\n\n')) {
    let event = 'message'
    const dataLines: string[] = []

    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }

    if (dataLines.length === 0) continue

    let payload: unknown
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      throw new AssistantChatError('invalid_response', true)
    }

    if (event === 'error') throw new AssistantChatError('server_error', true)
    if (event === 'delta') {
      if (
        typeof payload !== 'object' ||
        payload === null ||
        typeof (payload as Record<string, unknown>).text !== 'string'
      ) {
        throw new AssistantChatError('invalid_response', true)
      }
      answer.push((payload as { text: string }).text)
    }
    if (event === 'complete') completed = true
  }

  const text = answer.join('').trim()
  if (!completed || text.length === 0) throw new AssistantChatError('invalid_response', true)
  return text
}

export function createPublicChatClient(
  apiBaseUrl: string,
  assistantId: string,
  fetchImplementation: typeof globalThis.fetch = globalThis.fetch,
): AssistantChatClient {
  const baseUrl = apiBaseUrl.trim().replace(/\/+$/, '')
  const normalizedAssistantId = assistantId.trim()

  return {
    historyLimit: PUBLIC_HISTORY_LIMIT,
    async send(request, { signal }) {
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
            signal,
          },
        )
      } catch (error: unknown) {
        if (signal.aborted) throw error
        throw new AssistantChatError('network_error', true)
      }

      if (!response.ok) throw requestError(response.status)
      if (!response.headers.get('content-type')?.toLowerCase().includes('text/event-stream')) {
        throw new AssistantChatError('invalid_response', true)
      }

      return { answer: parseEventStream(await response.text()) }
    },
  }
}
