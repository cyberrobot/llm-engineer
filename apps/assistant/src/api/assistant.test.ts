import { describe, expect, it, vi } from 'vitest'

import { createAssistantApi } from './assistant'
import { AssistantApiError, HttpClient, type ApiLogger } from './client'

const logger: ApiLogger = {
  error: vi.fn(),
}

function createApi(fetchImplementation: typeof globalThis.fetch) {
  return createAssistantApi(
    new HttpClient({
      baseUrl: 'http://backend.test',
      fetch: fetchImplementation,
      logger,
    }),
  )
}

describe('Assistant API', () => {
  it('posts a typed chat request and returns the mock response', async () => {
    const fetchImplementation = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          message: 'Assistant backend connected successfully.',
          sources: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const api = createApi(fetchImplementation)

    await expect(api.chat({ message: 'Hello' })).resolves.toEqual({
      message: 'Assistant backend connected successfully.',
      sources: [],
    })
    expect(fetchImplementation).toHaveBeenCalledWith('http://backend.test/assistant/chat', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: 'Hello' }),
    })
  })

  it('converts non-success responses into a consistent API error', async () => {
    const api = createApi(
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 503 })),
    )

    const error = await api.chat({ message: 'Hello' }).catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(AssistantApiError)
    expect(error).toMatchObject({ code: 'HTTP_ERROR', status: 503 })
  })

  it('converts network failures into a consistent API error', async () => {
    const api = createApi(
      vi.fn<typeof globalThis.fetch>().mockRejectedValue(new TypeError('connection failed')),
    )

    const error = await api.chat({ message: 'Hello' }).catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(AssistantApiError)
    expect(error).toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('rejects malformed successful responses', async () => {
    const api = createApi(
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(
        new Response(JSON.stringify({ message: 42, sources: [] }), { status: 200 }),
      ),
    )

    const error = await api.chat({ message: 'Hello' }).catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(AssistantApiError)
    expect(error).toMatchObject({ code: 'INVALID_RESPONSE', status: 200 })
  })
})
