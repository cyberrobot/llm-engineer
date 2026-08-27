export interface PublicAssistantConfiguration {
  id: string
  name: string
  welcome_message: string
  input_placeholder: string
  suggested_questions: readonly string[]
  published_revision: number
}

export type PublicAssistantConfigurationErrorCode =
  | 'assistant_unavailable'
  | 'invalid_request'
  | 'invalid_response'
  | 'network_error'
  | 'server_error'

export class PublicAssistantConfigurationError extends Error {
  readonly code: PublicAssistantConfigurationErrorCode

  constructor(code: PublicAssistantConfigurationErrorCode) {
    super(code)
    this.name = 'PublicAssistantConfigurationError'
    this.code = code
  }
}

interface PublicAssistantClient {
  load(options: { signal: AbortSignal }): Promise<PublicAssistantConfiguration>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function parseConfiguration(value: unknown): PublicAssistantConfiguration {
  if (
    !isRecord(value) ||
    !isNonEmptyString(value.id) ||
    !isNonEmptyString(value.name) ||
    typeof value.welcome_message !== 'string' ||
    !isNonEmptyString(value.input_placeholder) ||
    !Array.isArray(value.suggested_questions) ||
    !value.suggested_questions.every(isNonEmptyString) ||
    !Number.isInteger(value.published_revision) ||
    (value.published_revision as number) < 1
  ) {
    throw new PublicAssistantConfigurationError('invalid_response')
  }
  return {
    id: value.id,
    name: value.name,
    welcome_message: value.welcome_message,
    input_placeholder: value.input_placeholder,
    suggested_questions: value.suggested_questions,
    published_revision: value.published_revision as number,
  }
}

export function createPublicAssistantClient(
  apiBaseUrl: string,
  assistantId: string,
  fetchImplementation: typeof globalThis.fetch = globalThis.fetch,
): PublicAssistantClient {
  const baseUrl = apiBaseUrl.trim().replace(/\/+$/, '')
  const normalizedAssistantId = assistantId.trim()

  return {
    async load({ signal }) {
      if (baseUrl.length === 0 || normalizedAssistantId.length === 0) {
        throw new PublicAssistantConfigurationError('invalid_request')
      }

      let response: Response
      try {
        response = await fetchImplementation(
          `${baseUrl}/public/assistants/${encodeURIComponent(normalizedAssistantId)}`,
          {
            method: 'GET',
            headers: { Accept: 'application/json' },
            cache: 'no-store',
            credentials: 'omit',
            signal,
          },
        )
      } catch (error: unknown) {
        if (signal.aborted) throw error
        throw new PublicAssistantConfigurationError('network_error')
      }

      if (response.status === 404) {
        throw new PublicAssistantConfigurationError('assistant_unavailable')
      }
      if (!response.ok) {
        throw new PublicAssistantConfigurationError('server_error')
      }

      let body: unknown
      try {
        body = await response.json()
      } catch {
        throw new PublicAssistantConfigurationError('invalid_response')
      }
      const configuration = parseConfiguration(body)
      if (configuration.id !== normalizedAssistantId) {
        throw new PublicAssistantConfigurationError('invalid_response')
      }
      return configuration
    },
  }
}
