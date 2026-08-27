import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AssistantWidgetDemo } from './AssistantWidgetDemo'

function eventStream(answer: string) {
  return new Response(
    [
      'event: start\ndata: {"assistant":"redmoor"}',
      `event: delta\ndata: ${JSON.stringify({ text: answer })}`,
      'event: complete\ndata: {"finishReason":"stop"}',
      '',
    ].join('\n\n'),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  )
}

function publicConfiguration() {
  return new Response(JSON.stringify({
    id: 'redmoor',
    name: 'Published Redmoor Assistant',
    welcome_message: 'Published welcome message.',
    input_placeholder: 'Ask the published assistant',
    suggested_questions: ['Published suggested question'],
    published_revision: 3,
  }))
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

describe('AssistantWidgetDemo', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_ASSISTANT_API_BASE_URL', 'https://api.example.test/base/')
    vi.stubEnv('VITE_ASSISTANT_ID', 'redmoor')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('renders the public widget with backend-managed published presentation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof globalThis.fetch>().mockResolvedValue(publicConfiguration()),
    )
    render(<AssistantWidgetDemo />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Connected assistant demo' }),
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('region', { name: 'Published Redmoor Assistant widget' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Published welcome message.')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Published suggested question' }),
    ).toBeInTheDocument()
    expect(screen.getByText('https://api.example.test/base')).toBeInTheDocument()
    expect(screen.getByText('redmoor')).toBeInTheDocument()
  })

  it('uses the real public client for a pending request and a multi-turn follow-up', async () => {
    const user = userEvent.setup()
    const firstResponse = deferredResponse()
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(publicConfiguration())
      .mockReturnValueOnce(firstResponse.promise)
      .mockResolvedValueOnce(eventStream('Second real answer.'))
    vi.stubGlobal('fetch', fetchImplementation)
    render(<AssistantWidgetDemo />)

    const input = await screen.findByRole('textbox', {
      name: 'Ask Published Redmoor Assistant a question',
    })
    await user.type(input, 'First question{Enter}')

    expect(screen.getByText('Thinking…')).toBeInTheDocument()
    expect(input).toBeDisabled()
    firstResponse.resolve(eventStream('First real answer.'))
    expect(await screen.findByText('First real answer.')).toBeInTheDocument()
    await user.type(input, 'Follow up{Enter}')
    expect(await screen.findByText('Second real answer.')).toBeInTheDocument()

    expect(fetchImplementation).toHaveBeenCalledTimes(3)
    expect(fetchImplementation.mock.calls[1]?.[0]).toBe(
      'https://api.example.test/base/public/assistants/redmoor/chat',
    )
    expect(JSON.parse(String(fetchImplementation.mock.calls[1]?.[1]?.body))).toEqual({
      message: 'First question',
      history: [],
    })
    expect(JSON.parse(String(fetchImplementation.mock.calls[2]?.[1]?.body))).toEqual({
      message: 'Follow up',
      history: [
        { role: 'user', content: 'First question' },
        { role: 'assistant', content: 'First real answer.' },
      ],
    })
  })

  it('routes a suggested question and retry through the same real client', async () => {
    const user = userEvent.setup()
    const fetchImplementation = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(publicConfiguration())
      .mockResolvedValueOnce(new Response('', { status: 500 }))
      .mockResolvedValueOnce(eventStream('Recovered real answer.'))
    vi.stubGlobal('fetch', fetchImplementation)
    render(<AssistantWidgetDemo />)

    await user.click(await screen.findByRole('button', { name: 'Published suggested question' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong while getting a response.',
    )
    await user.click(screen.getByRole('button', { name: 'Retry question' }))

    expect(await screen.findByText('Recovered real answer.')).toBeInTheDocument()
    expect(screen.getAllByText('Published suggested question')).toHaveLength(1)
    expect(fetchImplementation).toHaveBeenCalledTimes(3)
    expect(fetchImplementation.mock.calls[2]?.[0]).toBe(fetchImplementation.mock.calls[1]?.[0])
    expect(fetchImplementation.mock.calls[2]?.[1]?.body).toBe(
      fetchImplementation.mock.calls[1]?.[1]?.body,
    )
  })

  it(
    'shows named configuration guidance and does not render the widget when configuration is missing',
    () => {
      vi.stubEnv('VITE_ASSISTANT_API_BASE_URL', '')
      vi.stubEnv('VITE_ASSISTANT_ID', '')

      render(<AssistantWidgetDemo />)

      expect(
        screen.getByRole('heading', { name: 'Assistant demo configuration is incomplete' }),
      ).toBeInTheDocument()
      expect(
        screen.getByText(/VITE_ASSISTANT_API_BASE_URL=http:\/\/localhost:8000/),
      ).toBeInTheDocument()
      expect(screen.getByText(/VITE_ASSISTANT_ID=redmoor/)).toBeInTheDocument()
      expect(
        screen.queryByRole('region', { name: 'Redmoor Assistant widget' }),
      ).not.toBeInTheDocument()
    },
  )

  it('renders invalid URL guidance without crashing the demo route', () => {
    vi.stubEnv('VITE_ASSISTANT_API_BASE_URL', 'localhost:8000')

    expect(() => render(<AssistantWidgetDemo />)).not.toThrow()
    expect(
      screen.getByRole('heading', { name: 'Assistant demo configuration is invalid' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
