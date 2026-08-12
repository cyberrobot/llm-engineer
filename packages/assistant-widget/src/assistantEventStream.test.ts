import { describe, expect, it, vi } from 'vitest'

import { consumeAssistantEventStream } from './assistantEventStream'

function encodedStream(value: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(value))
      controller.close()
    },
  })
}

function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController
    },
  })
  return {
    close: () => controller.close(),
    enqueue: (value: string) => controller.enqueue(new TextEncoder().encode(value)),
    stream,
  }
}

describe('assistant event stream', () => {
  it('surfaces ordered deltas before completion and returns their exact concatenation', async () => {
    const controlled = controlledStream()
    const onDelta = vi.fn()
    const pending = consumeAssistantEventStream(controlled.stream, {
      signal: new AbortController().signal,
      onDelta,
    })

    controlled.enqueue('event: start\ndata: {"assistant":"redmoor"}\n\n')
    controlled.enqueue('event: delta\ndata: {"text":"Redmoor "}\n\n')
    await vi.waitFor(() => expect(onDelta).toHaveBeenCalledWith('Redmoor '))

    controlled.enqueue('event: delta\ndata: {"text":"helps."}\n\n')
    controlled.enqueue('event: complete\ndata: {"finishReason":"stop"}\n\n')

    await expect(pending).resolves.toEqual({ answer: 'Redmoor helps.' })
    expect(onDelta.mock.calls.map(([delta]) => delta)).toEqual(['Redmoor ', 'helps.'])
  })

  it.each([
    ['malformed JSON', 'event: start\ndata: {not-json}\n\n'],
    ['unknown event', 'event: surprise\ndata: {}\n\n'],
    ['delta before start', 'event: delta\ndata: {"text":"early"}\n\n'],
    ['duplicate start', 'event: start\ndata: {"assistant":"one"}\n\nevent: start\ndata: {"assistant":"two"}\n\n'],
    ['complete before start', 'event: complete\ndata: {"finishReason":"stop"}\n\n'],
    ['premature EOF', 'event: start\ndata: {"assistant":"redmoor"}\n\nevent: delta\ndata: {"text":"partial"}\n\n'],
  ])('rejects %s as an invalid response', async (_scenario, value) => {
    await expect(consumeAssistantEventStream(encodedStream(value), {
      signal: new AbortController().signal,
    })).rejects.toMatchObject({ code: 'invalid_response', retryable: true })
  })

  it('terminates safely on an explicit backend error event', async () => {
    await expect(consumeAssistantEventStream(encodedStream(
      'event: start\ndata: {"assistant":"redmoor"}\n\n' +
      'event: error\ndata: {"message":"private provider detail"}\n\n',
    ), { signal: new AbortController().signal })).rejects.toMatchObject({
      code: 'server_error',
      retryable: true,
      message: 'server_error',
    })
  })

  it('stops reading and emitting deltas after cancellation', async () => {
    const controlled = controlledStream()
    const controller = new AbortController()
    const onDelta = vi.fn()
    const pending = consumeAssistantEventStream(controlled.stream, {
      signal: controller.signal,
      onDelta,
    })
    controlled.enqueue('event: start\ndata: {"assistant":"redmoor"}\n\n')
    controlled.enqueue('event: delta\ndata: {"text":"partial"}\n\n')
    await vi.waitFor(() => expect(onDelta).toHaveBeenCalledOnce())

    controller.abort()

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(onDelta).toHaveBeenCalledOnce()
  })
})
