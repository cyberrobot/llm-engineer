import { useEffect, useMemo, useState } from 'react'

import type { AssistantWidgetProps } from './AssistantWidget.types'
import { AssistantWidgetConversation } from './components/assistant-widget/AssistantWidget'
import styles from './components/assistant-widget/AssistantWidget.module.css'
import {
  createPublicAssistantClient,
  type PublicAssistantConfiguration,
  PublicAssistantConfigurationError,
  type PublicAssistantConfigurationErrorCode,
} from './publicAssistantClient'
import { createPublicChatClient } from './publicChatClient'

type BootstrapState =
  | { key: string; status: 'loading' }
  | { configuration: PublicAssistantConfiguration; key: string; status: 'loaded' }
  | { code: PublicAssistantConfigurationErrorCode; key: string; status: 'error' }

function bootstrapErrorMessage(code: PublicAssistantConfigurationErrorCode): string {
  switch (code) {
    case 'assistant_unavailable':
      return 'This assistant is currently unavailable.'
    case 'network_error':
      return "We couldn't load the assistant. Please check your connection and try again."
    case 'invalid_request':
    case 'invalid_response':
    case 'server_error':
      return 'Something went wrong while loading the assistant.'
  }
}

function BootstrapStatus({ error }: { error?: PublicAssistantConfigurationErrorCode }) {
  return (
    <section className={styles.root} aria-label="Assistant widget">
      <div className={styles.header}>
        <p className={styles.title}>Assistant</p>
      </div>
      <div className={styles.configurationStatus} role={error ? 'alert' : 'status'}>
        {error ? bootstrapErrorMessage(error) : 'Loading assistant…'}
      </div>
    </section>
  )
}

export function AssistantWidget({
  assistantId,
  apiBaseUrl,
  assistantName,
  welcomeMessage,
  placeholder,
  suggestedQuestions,
}: AssistantWidgetProps) {
  const configurationKey = `${apiBaseUrl}\u0000${assistantId}`
  const publicAssistantClient = useMemo(
    () => createPublicAssistantClient(apiBaseUrl, assistantId),
    [apiBaseUrl, assistantId],
  )
  const chatClient = useMemo(
    () => createPublicChatClient(apiBaseUrl, assistantId),
    [apiBaseUrl, assistantId],
  )
  const [bootstrap, setBootstrap] = useState<BootstrapState>({
    key: configurationKey,
    status: 'loading',
  })

  useEffect(() => {
    const controller = new AbortController()
    void publicAssistantClient
      .load({ signal: controller.signal })
      .then((configuration) => {
        if (!controller.signal.aborted) {
          setBootstrap({ configuration, key: configurationKey, status: 'loaded' })
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setBootstrap({
          code:
            error instanceof PublicAssistantConfigurationError
              ? error.code
              : 'server_error',
          key: configurationKey,
          status: 'error',
        })
      })
    return () => controller.abort()
  }, [configurationKey, publicAssistantClient])

  if (bootstrap.key !== configurationKey || bootstrap.status === 'loading') {
    return <BootstrapStatus />
  }
  if (bootstrap.status === 'error') {
    return <BootstrapStatus error={bootstrap.code} />
  }

  const configuration = bootstrap.configuration

  return (
    <AssistantWidgetConversation
      assistantName={assistantName !== undefined ? assistantName : configuration.name}
      chatClient={chatClient}
      placeholder={placeholder !== undefined ? placeholder : configuration.input_placeholder}
      suggestedQuestions={
        suggestedQuestions !== undefined
          ? suggestedQuestions
          : configuration.suggested_questions
      }
      welcomeMessage={
        welcomeMessage !== undefined ? welcomeMessage : configuration.welcome_message
      }
    />
  )
}
