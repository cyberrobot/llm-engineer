import type { AssistantChatHistoryMessage, AssistantMessage } from './AssistantWidget.types'

export interface StatefulConversationMessage extends AssistantMessage {
  status: 'complete' | 'pending' | 'failed'
  presentationOnly?: boolean
}

export function buildConversationHistory(
  messages: readonly StatefulConversationMessage[],
  limit: number,
  currentMessageId?: string,
): AssistantChatHistoryMessage[] {
  if (!Number.isInteger(limit) || limit < 0) return []

  const eligible = messages
    .filter(
      (message) =>
        message.status === 'complete' &&
        !message.presentationOnly &&
        message.id !== currentMessageId,
    )
    .map(({ role, content }) => ({ role, content }))

  return limit === 0 ? [] : eligible.slice(-limit)
}
