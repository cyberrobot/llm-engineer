export type ApiErrorCode = 'NETWORK_ERROR' | 'HTTP_ERROR' | 'INVALID_RESPONSE'

export class AssistantApiError extends Error {
  readonly code: ApiErrorCode
  readonly status?: number

  constructor(code: ApiErrorCode, message: string, status?: number) {
    super(message)
    this.name = 'AssistantApiError'
    this.code = code
    this.status = status
  }
}

export interface ApiLogger {
  error(message: string, context: { code: ApiErrorCode; status?: number }): void
}

export interface HttpClientOptions {
  baseUrl: string
  fetch?: typeof globalThis.fetch
  logger?: ApiLogger
}

const defaultLogger: ApiLogger = {
  error(message, context) {
    console.error(message, context)
  },
}

export class HttpClient {
  private readonly baseUrl: string
  private readonly fetchImplementation: typeof globalThis.fetch
  private readonly logger: ApiLogger

  constructor({ baseUrl, fetch: fetchImplementation = globalThis.fetch, logger }: HttpClientOptions) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.fetchImplementation = fetchImplementation
    this.logger = logger ?? defaultLogger
  }

  async post<TRequest, TResponse>(
    path: string,
    body: TRequest,
    isResponse: (value: unknown) => value is TResponse,
  ): Promise<TResponse> {
    let response: Response

    try {
      response = await this.fetchImplementation(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
    } catch {
      throw this.report(
        new AssistantApiError('NETWORK_ERROR', 'Unable to connect to the Assistant service.'),
      )
    }

    if (!response.ok) {
      throw this.report(
        new AssistantApiError(
          'HTTP_ERROR',
          'The Assistant service could not complete the request.',
          response.status,
        ),
      )
    }

    let value: unknown
    try {
      value = await response.json()
    } catch {
      throw this.report(
        new AssistantApiError(
          'INVALID_RESPONSE',
          'The Assistant service returned an invalid response.',
          response.status,
        ),
      )
    }

    if (!isResponse(value)) {
      throw this.report(
        new AssistantApiError(
          'INVALID_RESPONSE',
          'The Assistant service returned an invalid response.',
          response.status,
        ),
      )
    }

    return value
  }

  private report(error: AssistantApiError): AssistantApiError {
    this.logger.error('Assistant API request failed.', {
      code: error.code,
      ...(error.status === undefined ? {} : { status: error.status }),
    })
    return error
  }
}
