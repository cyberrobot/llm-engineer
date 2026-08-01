import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AssistantWidget } from './AssistantWidget'
import {
  AssistantChatError,
  type AssistantChatClient,
  type AssistantChatResponse,
} from './AssistantWidget.types'

function deferredPromise() {
  let resolve!: () => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<void>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, reject, resolve }
}

function deferredResponse() {
  let resolve!: (response: AssistantChatResponse) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<AssistantChatResponse>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, reject, resolve }
}

function mockClient(
  send: AssistantChatClient['send'],
  historyLimit = 10,
): AssistantChatClient {
  return { historyLimit, send }
}

describe('AssistantWidget', () => {
  it('renders its default welcome message and accessible composer', () => {
    render(<AssistantWidget />)

    expect(screen.getByText('How can I help you today?')).toBeInTheDocument()
    expect(screen.getByRole('log', { name: 'Assistant conversation' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Assistant a question' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveAttribute('maxlength', '2000')
  })

  it('allows the host to override user-facing text', () => {
    render(
      <AssistantWidget
        assistantName="Redmoor Guide"
        placeholder="Ask about consulting…"
        welcomeMessage="Welcome to Redmoor."
      />,
    )

    expect(screen.getByText('Welcome to Redmoor.')).toBeInTheDocument()
    expect(screen.getByRole('log', { name: 'Redmoor Guide conversation' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Ask Redmoor Guide a question' })).toHaveAttribute(
      'placeholder',
      'Ask about consulting…',
    )
  })

  it('renders supplied suggestions and omits the suggestion group when none are supplied', () => {
    const { rerender } = render(
      <AssistantWidget suggestedQuestions={['What services do you offer?']} />,
    )

    expect(screen.getByRole('group', { name: 'Suggested questions' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'What services do you offer?' })).toBeInTheDocument()

    rerender(<AssistantWidget suggestedQuestions={[]} />)

    expect(screen.queryByRole('group', { name: 'Suggested questions' })).not.toBeInTheDocument()
  })

  it.each(['', '   \n  '])('does not submit empty input %j', async (value) => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AssistantWidget onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox')
    if (value) await user.type(input, value)
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(within(screen.getByRole('log')).queryByText('You')).not.toBeInTheDocument()
  })

  it('submits trimmed text with the button, renders it, and clears the composer', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AssistantWidget onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox')
    await user.type(input, '  Tell me about Redmoor  ')
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith('Tell me about Redmoor')
    expect(within(screen.getByRole('log')).getByText('Tell me about Redmoor')).toBeInTheDocument()
    expect(input).toHaveValue('')
  })

  it('submits with Enter and preserves a newline with Shift+Enter', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AssistantWidget onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'First line{Shift>}{Enter}{/Shift}Second line')
    expect(input).toHaveValue('First line\nSecond line')
    expect(onSubmit).not.toHaveBeenCalled()

    await user.type(input, '{Enter}')

    expect(onSubmit).toHaveBeenCalledWith('First line\nSecond line')
  })

  it('prevents duplicate asynchronous submissions and restores the composer on resolve', async () => {
    const user = userEvent.setup()
    const pending = deferredPromise()
    const onSubmit = vi.fn(() => pending.promise)
    render(<AssistantWidget onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox')
    const submit = screen.getByRole('button', { name: 'Send message' })
    await user.type(input, 'A pending question')
    await user.click(submit)

    expect(onSubmit).toHaveBeenCalledOnce()
    expect(input).toBeDisabled()
    expect(submit).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Sending message')
    await user.click(submit)
    expect(onSubmit).toHaveBeenCalledOnce()

    pending.resolve()

    await waitFor(() => expect(input).toBeEnabled())
    expect(input).toHaveValue('')
    expect(submit).toBeDisabled()
  })

  it('preserves the message and restores the composer when submission rejects', async () => {
    const user = userEvent.setup()
    const pending = deferredPromise()
    const error = new Error('provider details must not be rendered')
    const onError = vi.fn()
    render(<AssistantWidget onSubmit={() => pending.promise} onError={onError} />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'Keep this question')
    await user.type(input, '{Enter}')
    pending.reject(error)

    await waitFor(() => expect(input).toBeEnabled())
    expect(input).toHaveValue('Keep this question')
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled()
    expect(within(screen.getByRole('log')).getByText('Keep this question')).toBeInTheDocument()
    expect(onError).toHaveBeenCalledWith(error)
    expect(screen.queryByText(error.message)).not.toBeInTheDocument()
  })

  it('submits a suggested question once from the keyboard and then hides suggestions', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <AssistantWidget
        onSubmit={onSubmit}
        suggestedQuestions={['Can you help with an AI assistant?']}
      />,
    )

    const suggestion = screen.getByRole('button', {
      name: 'Can you help with an AI assistant?',
    })
    suggestion.focus()
    await user.keyboard('{Enter}')

    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onSubmit).toHaveBeenCalledWith('Can you help with an AI assistant?')
    expect(screen.queryByRole('group', { name: 'Suggested questions' })).not.toBeInTheDocument()
  })

  it('renders a host-controlled conversation without adding a duplicate user message', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <AssistantWidget
        messages={[{ id: 'answer-1', role: 'assistant', content: 'A supplied answer' }]}
        onSubmit={onSubmit}
      />,
    )

    await user.type(screen.getByRole('textbox'), 'Controlled question{Enter}')

    expect(onSubmit).toHaveBeenCalledWith('Controlled question')
    expect(within(screen.getByRole('log')).queryByText('Controlled question')).not.toBeInTheDocument()
  })

  it('shows a submitted question immediately and appends the mocked response', async () => {
    const user = userEvent.setup()
    const response = deferredResponse()
    const client = mockClient(vi.fn(() => response.promise))
    render(<AssistantWidget chatClient={client} />)

    const input = screen.getByRole('textbox')
    await user.type(input, 'What does Redmoor offer?{Enter}')

    expect(screen.getByText('What does Redmoor offer?')).toBeInTheDocument()
    expect(screen.getByText('Thinking…')).toBeInTheDocument()
    expect(input).toBeDisabled()
    expect(client.send).toHaveBeenCalledWith(
      { message: 'What does Redmoor offer?', history: [] },
      { signal: expect.any(AbortSignal) },
    )

    response.resolve({ answer: 'Practical technology consulting.' })

    expect(await screen.findByText('Practical technology consulting.')).toBeInTheDocument()
    await waitFor(() => expect(input).toBeEnabled())
    expect(input).toHaveFocus()
  })

  it('sends bounded successful history with a follow-up question', async () => {
    const user = userEvent.setup()
    const send = vi
      .fn<AssistantChatClient['send']>()
      .mockResolvedValueOnce({ answer: 'First answer' })
      .mockResolvedValueOnce({ answer: 'Second answer' })
    render(<AssistantWidget chatClient={mockClient(send, 2)} />)

    await user.type(screen.getByRole('textbox'), 'First question{Enter}')
    await screen.findByText('First answer')
    await user.type(screen.getByRole('textbox'), 'Follow up{Enter}')
    await screen.findByText('Second answer')

    expect(send).toHaveBeenNthCalledWith(
      2,
      {
        message: 'Follow up',
        history: [
          expect.objectContaining({ role: 'user', content: 'First question' }),
          expect.objectContaining({ role: 'assistant', content: 'First answer' }),
        ],
      },
      { signal: expect.any(AbortSignal) },
    )
  })

  it('routes a suggested question through the same single-flight chat client', async () => {
    const user = userEvent.setup()
    const response = deferredResponse()
    const send = vi.fn<AssistantChatClient['send']>(() => response.promise)
    render(
      <AssistantWidget
        chatClient={mockClient(send)}
        suggestedQuestions={['What services do you offer?']}
      />,
    )

    const suggestion = screen.getByRole('button', { name: 'What services do you offer?' })
    await user.dblClick(suggestion)

    expect(send).toHaveBeenCalledOnce()
    expect(send.mock.calls[0]?.[0]).toEqual({
      message: 'What services do you offer?',
      history: [],
    })
    expect(screen.queryByRole('group', { name: 'Suggested questions' })).not.toBeInTheDocument()
    response.resolve({ answer: 'Consulting services.' })
    expect(await screen.findByText('Consulting services.')).toBeInTheDocument()
  })

  it('keeps a failed question and retries it without adding a duplicate', async () => {
    const user = userEvent.setup()
    const send = vi
      .fn<AssistantChatClient['send']>()
      .mockRejectedValueOnce(new AssistantChatError('network_error', true))
      .mockResolvedValueOnce({ answer: 'Recovered answer' })
    render(<AssistantWidget chatClient={mockClient(send)} />)

    await user.type(screen.getByRole('textbox'), 'Please keep me{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent("We couldn't reach the assistant")
    expect(screen.getAllByText('Please keep me')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Retry question' }))

    expect(await screen.findByText('Recovered answer')).toBeInTheDocument()
    expect(screen.getAllByText('Please keep me')).toHaveLength(1)
    expect(send).toHaveBeenCalledTimes(2)
    expect(send.mock.calls[1]?.[0]).toEqual({ message: 'Please keep me', history: [] })
  })

  it('does not offer retry for a non-retryable unavailable assistant', async () => {
    const user = userEvent.setup()
    const client = mockClient(
      vi.fn(() => Promise.reject(new AssistantChatError('assistant_unavailable', false))),
    )
    render(<AssistantWidget chatClient={client} />)

    await user.type(screen.getByRole('textbox'), 'Hello{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('currently unavailable')
    expect(screen.queryByRole('button', { name: 'Retry question' })).not.toBeInTheDocument()
  })

  it('aborts an active request on unmount without showing an error', async () => {
    const user = userEvent.setup()
    let signal: AbortSignal | undefined
    const response = deferredResponse()
    const client = mockClient(
      vi.fn((_request, options) => {
        signal = options.signal
        return response.promise
      }),
    )
    const { unmount } = render(<AssistantWidget chatClient={client} />)
    await user.type(screen.getByRole('textbox'), 'Pending{Enter}')

    unmount()

    expect(signal?.aborted).toBe(true)
    response.reject(new DOMException('Aborted', 'AbortError'))
  })

  it('aborts and resets when the configured client changes', async () => {
    const user = userEvent.setup()
    const oldResponse = deferredResponse()
    let oldSignal: AbortSignal | undefined
    const oldClient = mockClient(
      vi.fn((_request, options) => {
        oldSignal = options.signal
        return oldResponse.promise
      }),
    )
    const newClient = mockClient(vi.fn(() => Promise.resolve({ answer: 'New answer' })))
    const { rerender } = render(
      <AssistantWidget chatClient={oldClient} welcomeMessage="Old welcome" />,
    )
    await user.type(screen.getByRole('textbox'), 'Old question{Enter}')

    rerender(<AssistantWidget chatClient={newClient} welcomeMessage="New welcome" />)

    expect(oldSignal?.aborted).toBe(true)
    expect(screen.getByText('New welcome')).toBeInTheDocument()
    expect(screen.queryByText('Old question')).not.toBeInTheDocument()
    oldResponse.resolve({ answer: 'Stale answer' })
    await Promise.resolve()
    expect(screen.queryByText('Stale answer')).not.toBeInTheDocument()
  })

  it('rejects an over-limit question without calling the client', () => {
    const client = mockClient(vi.fn())
    render(<AssistantWidget chatClient={client} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'x'.repeat(2_001) } })
    fireEvent.submit(input.closest('form')!)

    expect(client.send).not.toHaveBeenCalled()
    expect(screen.getByText('Questions must be 2000 characters or fewer.')).toBeInTheDocument()
  })

  it('treats a malformed mocked success as a safe retryable failure', async () => {
    const user = userEvent.setup()
    const client = mockClient(vi.fn(() => Promise.resolve({ answer: '  ' })))
    render(<AssistantWidget chatClient={client} />)

    await user.type(screen.getByRole('textbox'), 'Question{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong while getting a response.',
    )
    expect(screen.getByRole('button', { name: 'Retry question' })).toBeInTheDocument()
  })
})
