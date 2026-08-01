import { useMemo } from 'react'

import type { AssistantWidgetProps } from './AssistantWidget.types'
import { AssistantWidgetConversation } from './components/assistant-widget/AssistantWidget'
import { createPublicChatClient } from './publicChatClient'

export function AssistantWidget({
  assistantId,
  apiBaseUrl,
  assistantName,
  welcomeMessage,
  placeholder,
  suggestedQuestions,
}: AssistantWidgetProps) {
  const chatClient = useMemo(
    () => createPublicChatClient(apiBaseUrl, assistantId),
    [apiBaseUrl, assistantId],
  )

  return (
    <AssistantWidgetConversation
      assistantName={assistantName}
      chatClient={chatClient}
      placeholder={placeholder}
      suggestedQuestions={suggestedQuestions}
      welcomeMessage={welcomeMessage}
    />
  )
}
