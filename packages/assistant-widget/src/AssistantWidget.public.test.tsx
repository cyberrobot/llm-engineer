import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AssistantWidget } from './AssistantWidget'

afterEach(() => vi.unstubAllGlobals())

describe('public AssistantWidget', () => {
  it('uses consumer configuration to render and call the public assistant API', async () => {
    const fetchImplementation = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(
        [
          'event: start\ndata: {"assistant":"test-assistant"}',
          'event: delta\ndata: {"text":"Configured answer"}',
          'event: complete\ndata: {"finishReason":"stop"}',
          '',
        ].join('\n\n'),
        { headers: { 'Content-Type': 'text/event-stream' } },
      ),
    )
    vi.stubGlobal('fetch', fetchImplementation)
    const user = userEvent.setup()

    render(
      <AssistantWidget
        apiBaseUrl="https://api.example.test"
        assistantId="test-assistant"
        assistantName="Test Assistant"
      />,
    )
    await user.type(screen.getByRole('textbox', { name: 'Ask Test Assistant a question' }), 'Hello{Enter}')

    expect(await screen.findByText('Configured answer')).toBeInTheDocument()
    expect(fetchImplementation).toHaveBeenCalledOnce()
    expect(fetchImplementation.mock.calls[0]?.[0]).toBe(
      'https://api.example.test/public/assistants/test-assistant/chat',
    )
  })
})
