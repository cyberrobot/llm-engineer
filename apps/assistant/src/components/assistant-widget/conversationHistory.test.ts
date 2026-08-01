import { describe, expect, it } from 'vitest'

import { buildConversationHistory, type StatefulConversationMessage } from './conversationHistory'

const messages: readonly StatefulConversationMessage[] = [
  { id: 'welcome', role: 'assistant', content: 'Welcome', status: 'complete', presentationOnly: true },
  { id: 'user-1', role: 'user', content: 'First', status: 'complete' },
  { id: 'assistant-1', role: 'assistant', content: 'Answer', status: 'complete' },
  { id: 'pending', role: 'user', content: 'Pending', status: 'pending' },
  { id: 'failed', role: 'assistant', content: 'Failed answer', status: 'failed' },
  { id: 'current', role: 'user', content: 'Current', status: 'complete' },
]

describe('buildConversationHistory', () => {
  it('returns an empty history for the first question', () => {
    expect(buildConversationHistory(messages.slice(0, 1), 10)).toEqual([])
  })

  it('includes only completed conversational messages without duplicating the current question', () => {
    expect(buildConversationHistory(messages, 10, 'current')).toEqual([
      { role: 'user', content: 'First' },
      { role: 'assistant', content: 'Answer' },
    ])
  })

  it('keeps chronological order while applying the client-provided limit', () => {
    expect(buildConversationHistory(messages, 1, 'current')).toEqual([
      { role: 'assistant', content: 'Answer' },
    ])
  })
})
