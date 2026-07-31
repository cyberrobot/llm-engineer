import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AssistantWidget } from './AssistantWidget'

function deferredPromise() {
  let resolve!: () => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<void>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, reject, resolve }
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
})
