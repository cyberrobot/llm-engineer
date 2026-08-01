import { describe, expect, it, vi } from 'vitest'

import { createPublicChatClient } from './publicChatClient'

function eventStream(...events: string[]) {
  return new Response(events.join('\n\n') + '\n\n', {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
  })
}

describe('public assistant chat client', () => {
  it('posts bounded history to the configured assistant and returns completed SSE text', async () => {
    const fetchImplementation = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      eventStream(
        'event: start\ndata: {"assistant":"public-example"}',
        'event: delta\ndata: {"text":"A useful "}',
        'event: delta\ndata: {"text":"answer."}',
        'event: complete\ndata: {"finishReason":"stop"}',
      ),
    )
    const client = createPublicChatClient(
      'https://api.example.test/',
      'public example',
      fetchImplementation,
    )
    const signal = new AbortController().signal

    await expect(
      client.send(
        {
          message: 'Question',
          history: [
            { role: 'user', content: 'Earlier question' },
            { role: 'assistant', content: 'Earlier answer' },
          ],
        },
        { signal },
      ),
    ).resolves.toEqual({ answer: 'A useful answer.' })
    expect(client.historyLimit).toBe(12)
    expect(fetchImplementation).toHaveBeenCalledWith(
      'https://api.example.test/public/assistants/public%20example/chat',
      {
        method: 'POST',
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: 'Question',
          history: [
            { role: 'user', content: 'Earlier question' },
            { role: 'assistant', content: 'Earlier answer' },
          ],
        }),
        signal,
      },
    )
  })

  it.each([
    [404, 'assistant_unavailable', false],
    [422, 'invalid_request', false],
    [429, 'rate_limited', true],
    [500, 'server_error', true],
  ])('maps HTTP %i to a safe %s failure', async (status, code, retryable) => {
    const client = createPublicChatClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('private detail', { status })),
    )

    await expect(
      client.send({ message: 'Question', history: [] }, { signal: new AbortController().signal }),
    ).rejects.toMatchObject({ code, retryable })
  })

  it('rejects malformed or incomplete event streams without exposing response content', async () => {
    const client = createPublicChatClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(
        eventStream('event: delta\ndata: {"private":"provider detail"}'),
      ),
    )

    const error = await client
      .send({ message: 'Question', history: [] }, { signal: new AbortController().signal })
      .catch((reason: unknown) => reason)

    expect(error).toMatchObject({ code: 'invalid_response', retryable: true })
    expect(String(error)).not.toContain('provider detail')
  })

  it('maps network failures while preserving request cancellation', async () => {
    const networkClient = createPublicChatClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockRejectedValue(new TypeError('private network detail')),
    )
    await expect(
      networkClient.send(
        { message: 'Question', history: [] },
        { signal: new AbortController().signal },
      ),
    ).rejects.toMatchObject({ code: 'network_error', retryable: true })

    const controller = new AbortController()
    controller.abort()
    const abortError = new DOMException('Aborted', 'AbortError')
    const abortedClient = createPublicChatClient(
      'https://api.example.test',
      'redmoor',
      vi.fn<typeof globalThis.fetch>().mockRejectedValue(abortError),
    )
    await expect(
      abortedClient.send({ message: 'Question', history: [] }, { signal: controller.signal }),
    ).rejects.toBe(abortError)
  })
})
