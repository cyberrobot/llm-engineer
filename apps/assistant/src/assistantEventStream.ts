import {
  AssistantChatError,
  type AssistantChatResponse,
} from './components/assistant-widget/AssistantWidget.types'

export interface AssistantEventStreamOptions {
  signal: AbortSignal
  onStart?: () => void
  onDelta?: (delta: string) => void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(value)
  return keys.length === expected.length && expected.every((key) => keys.includes(key))
}

function invalidResponse(): AssistantChatError {
  return new AssistantChatError('invalid_response', true)
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError')
}

export async function consumeAssistantEventStream(
  stream: ReadableStream<Uint8Array> | null,
  options: AssistantEventStreamOptions,
): Promise<AssistantChatResponse> {
  if (!stream) throw invalidResponse()
  if (options.signal.aborted) throw abortError()

  const reader = stream.getReader()
  const decoder = new TextDecoder()
  const answer: string[] = []
  let started = false
  let completed = false
  let input = ''
  let eventName = 'message'
  let dataLines: string[] = []

  const cancel = () => {
    void reader.cancel().catch(() => undefined)
  }
  options.signal.addEventListener('abort', cancel, { once: true })

  function dispatchEvent() {
    if (options.signal.aborted) throw abortError()
    if (dataLines.length === 0) {
      eventName = 'message'
      return
    }

    let payload: unknown
    try {
      payload = JSON.parse(dataLines.join('\n'))
    } catch {
      throw invalidResponse()
    } finally {
      dataLines = []
    }

    const currentEvent = eventName
    eventName = 'message'
    if (completed) throw invalidResponse()
    if (!['start', 'delta', 'complete', 'error'].includes(currentEvent)) {
      throw invalidResponse()
    }
    if (currentEvent === 'error') throw new AssistantChatError('server_error', true)
    if (currentEvent === 'start') {
      if (
        started ||
        !isRecord(payload) ||
        !hasExactKeys(payload, ['assistant']) ||
        typeof payload.assistant !== 'string' ||
        payload.assistant.length === 0
      ) {
        throw invalidResponse()
      }
      started = true
      options.onStart?.()
      return
    }
    if (currentEvent === 'delta') {
      if (
        !started ||
        !isRecord(payload) ||
        !hasExactKeys(payload, ['text']) ||
        typeof payload.text !== 'string'
      ) {
        throw invalidResponse()
      }
      answer.push(payload.text)
      options.onDelta?.(payload.text)
      return
    }
    if (
      !started ||
      !isRecord(payload) ||
      !hasExactKeys(payload, ['finishReason']) ||
      payload.finishReason !== 'stop' ||
      answer.join('').trim().length === 0
    ) {
      throw invalidResponse()
    }
    completed = true
  }

  function processLine(line: string) {
    if (line.endsWith('\r')) line = line.slice(0, -1)
    if (line.length === 0) {
      dispatchEvent()
      return
    }
    if (line.startsWith(':')) return

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventName = value
    if (field === 'data') dataLines.push(value)
  }

  try {
    while (!completed) {
      let result: ReadableStreamReadResult<Uint8Array>
      try {
        result = await reader.read()
      } catch (error: unknown) {
        if (options.signal.aborted) throw abortError()
        if (error instanceof AssistantChatError) throw error
        throw new AssistantChatError('network_error', true)
      }
      if (options.signal.aborted) throw abortError()
      if (result.done) {
        input += decoder.decode()
        if (input.length > 0) processLine(input)
        if (dataLines.length > 0) dispatchEvent()
        break
      }

      input += decoder.decode(result.value, { stream: true })
      let lineBreak = input.indexOf('\n')
      while (lineBreak !== -1) {
        const line = input.slice(0, lineBreak)
        input = input.slice(lineBreak + 1)
        processLine(line)
        if (completed) break
        lineBreak = input.indexOf('\n')
      }
    }

    if (!completed) throw invalidResponse()
    return { answer: answer.join('') }
  } finally {
    options.signal.removeEventListener('abort', cancel)
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
