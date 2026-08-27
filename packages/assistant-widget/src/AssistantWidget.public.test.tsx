import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AssistantWidget } from './AssistantWidget'

afterEach(() => vi.unstubAllGlobals())

function configuration(overrides: Record<string, unknown> = {}) {
  return new Response(JSON.stringify({
    id: 'test-assistant',
    name: 'Server Assistant',
    welcome_message: 'Welcome from server',
    input_placeholder: 'Ask the server assistant',
    suggested_questions: ['Server question'],
    published_revision: 7,
    ...overrides,
  }))
}

function eventStream(answer = 'Configured answer') {
  return new Response(
    [
      'event: start\ndata: {"assistant":"test-assistant"}',
      `event: delta\ndata: ${JSON.stringify({ text: answer })}`,
      'event: complete\ndata: {"finishReason":"stop"}',
      '',
    ].join('\n\n'),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
}

describe('public AssistantWidget', () => {
  it('loads published presentation before rendering and keeps chat on the existing route', async () => {
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(configuration())
      .mockResolvedValueOnce(eventStream())
    vi.stubGlobal('fetch', fetchImplementation)
    const user = userEvent.setup()

    render(<AssistantWidget apiBaseUrl="https://api.example.test/" assistantId="test-assistant" />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading assistant…')
    expect(screen.queryByText('Welcome from server')).not.toBeInTheDocument()
    expect(await screen.findByText('Welcome from server')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Server Assistant widget' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Server question' })).toBeInTheDocument()
    const input = screen.getByRole('textbox', { name: 'Ask Server Assistant a question' })
    expect(input).toHaveAttribute('placeholder', 'Ask the server assistant')
    await user.type(input, 'Hello{Enter}')

    expect(await screen.findByText('Configured answer')).toBeInTheDocument()
    expect(fetchImplementation).toHaveBeenCalledTimes(2)
    expect(fetchImplementation.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/public/assistants/test-assistant',
    )
    expect(fetchImplementation.mock.calls[1]?.[0]).toBe(
      'https://api.example.test/public/assistants/test-assistant/chat',
    )
  })

  it('applies explicit presentation overrides using undefined rather than truthiness', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(configuration()),
    )

    render(
      <AssistantWidget
        apiBaseUrl="https://api.example.test"
        assistantId="test-assistant"
        assistantName="Host Assistant"
        placeholder="Host placeholder"
        suggestedQuestions={[]}
        welcomeMessage=""
      />,
    )

    expect(await screen.findByRole('region', { name: 'Host Assistant widget' })).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'Host placeholder')
    expect(screen.queryByText('Welcome from server')).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Suggested questions' })).not.toBeInTheDocument()
  })

  it.each([
    [404, 'This assistant is currently unavailable.'],
    [500, 'Something went wrong while loading the assistant.'],
  ])('shows a safe configuration state for HTTP %i without rendering overrides', async (status, message) => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('private detail', { status })),
    )

    render(
      <AssistantWidget
        apiBaseUrl="https://api.example.test"
        assistantId="test-assistant"
        welcomeMessage="Stale host welcome"
      />,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByText('Stale host welcome')).not.toBeInTheDocument()
  })

  it('shows safe network and malformed-response configuration errors', async () => {
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockRejectedValueOnce(new TypeError('private network detail'))
      .mockResolvedValueOnce(configuration({ suggested_questions: [12] }))
    vi.stubGlobal('fetch', fetchImplementation)

    const { rerender } = render(
      <AssistantWidget apiBaseUrl="https://api.example.test" assistantId="network" />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "We couldn't load the assistant. Please check your connection and try again.",
    )

    rerender(<AssistantWidget apiBaseUrl="https://api.example.test" assistantId="malformed" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong while loading the assistant.',
    )
    expect(screen.queryByText('12')).not.toBeInTheDocument()
  })

  it('still surfaces chat unavailability after configuration has loaded', async () => {
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(configuration())
      .mockResolvedValueOnce(new Response('', { status: 404 }))
    vi.stubGlobal('fetch', fetchImplementation)
    const user = userEvent.setup()

    render(
      <AssistantWidget apiBaseUrl="https://api.example.test" assistantId="test-assistant" />,
    )
    await user.type(await screen.findByRole('textbox'), 'Is this still available?{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This assistant is currently unavailable.',
    )
    expect(fetchImplementation.mock.calls[1]?.[0]).toBe(
      'https://api.example.test/public/assistants/test-assistant/chat',
    )
  })

  it('aborts an in-flight bootstrap when unmounted', async () => {
    let requestSignal: AbortSignal | undefined
    const fetchImplementation = vi.fn<typeof globalThis.fetch>((_input, init) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>(() => undefined)
    })
    vi.stubGlobal('fetch', fetchImplementation)

    const { unmount } = render(
      <AssistantWidget apiBaseUrl="https://api.example.test" assistantId="test-assistant" />,
    )
    await waitFor(() => expect(requestSignal).toBeDefined())
    act(unmount)

    expect(requestSignal?.aborted).toBe(true)
  })
})
