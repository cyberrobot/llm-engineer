import { describe, expect, it, vi } from 'vitest'

import { createPublicAssistantClient } from './publicAssistantClient'

function configuration(overrides: Record<string, unknown> = {}) {
  return {
    id: 'redmoor',
    name: 'Redmoor Assistant',
    welcome_message: 'Welcome from server',
    input_placeholder: 'Ask Redmoor',
    suggested_questions: ['Question one', 'Question two'],
    published_revision: 7,
    ...overrides,
  }
}

describe('public assistant configuration client', () => {
  it.each([
    ['https://api.example.test', 'redmoor', 'https://api.example.test/public/assistants/redmoor'],
    ['https://api.example.test/', 'public example', 'https://api.example.test/public/assistants/public%20example'],
  ])('loads and validates configuration from %s', async (baseUrl, assistantId, expectedUrl) => {
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValue(new Response(JSON.stringify(configuration({ id: assistantId }))))
    const client = createPublicAssistantClient(baseUrl, assistantId, fetchImplementation)
    const signal = new AbortController().signal

    await expect(client.load({ signal })).resolves.toEqual(configuration({ id: assistantId }))
    expect(fetchImplementation).toHaveBeenCalledWith(expectedUrl, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      credentials: 'omit',
      signal,
    })
  })

  it.each([
    [{ id: '' }],
    [{ id: 'another-assistant' }],
    [{ name: null }],
    [{ welcome_message: 12 }],
    [{ input_placeholder: null }],
    [{ suggested_questions: ['valid', 2] }],
    [{ published_revision: 0 }],
    [{ published_revision: 1.5 }],
  ])('rejects malformed successful configuration %j', async (override) => {
    const client = createPublicAssistantClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(
        new Response(JSON.stringify(configuration(override))),
      ),
    )

    await expect(client.load({ signal: new AbortController().signal })).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('maps unavailable, server, network, and cancelled requests safely', async () => {
    const signal = new AbortController().signal
    const unavailable = createPublicAssistantClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('private', { status: 404 })),
    )
    await expect(unavailable.load({ signal })).rejects.toMatchObject({
      code: 'assistant_unavailable',
    })

    const server = createPublicAssistantClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('private', { status: 500 })),
    )
    await expect(server.load({ signal })).rejects.toMatchObject({ code: 'server_error' })

    const network = createPublicAssistantClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockRejectedValue(new TypeError('private network detail')),
    )
    await expect(network.load({ signal })).rejects.toMatchObject({ code: 'network_error' })

    const controller = new AbortController()
    controller.abort()
    const abortError = new DOMException('Aborted', 'AbortError')
    const cancelled = createPublicAssistantClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockRejectedValue(abortError),
    )
    await expect(cancelled.load({ signal: controller.signal })).rejects.toBe(abortError)
  })
})
