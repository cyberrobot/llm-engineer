import { useId, useRef, useState } from 'react'

import type { AssistantMessage, AssistantWidgetProps } from './AssistantWidget.types'
import styles from './AssistantWidget.module.css'
import { ConversationMessage } from './ConversationMessage'
import { MessageComposer } from './MessageComposer'
import { SuggestedFollowUps } from './SuggestedFollowUps'

const DEFAULT_ASSISTANT_NAME = 'Assistant'
const DEFAULT_WELCOME_MESSAGE = 'How can I help you today?'
const DEFAULT_PLACEHOLDER = 'Ask a question…'

function isPromise(value: void | Promise<void>): value is Promise<void> {
  return value !== undefined && typeof value.then === 'function'
}

export function AssistantWidget({
  assistantName = DEFAULT_ASSISTANT_NAME,
  welcomeMessage = DEFAULT_WELCOME_MESSAGE,
  placeholder = DEFAULT_PLACEHOLDER,
  suggestedQuestions = [],
  messages,
  onSubmit,
  onError,
}: AssistantWidgetProps) {
  const instanceId = useId()
  const nextMessageNumber = useRef(0)
  const pendingRef = useRef(false)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [hasSubmitted, setHasSubmitted] = useState(false)
  const [localMessages, setLocalMessages] = useState<readonly AssistantMessage[]>([
    { id: `${instanceId}-welcome`, role: 'assistant', content: welcomeMessage },
  ])
  const visibleMessages = messages ?? localMessages
  const hasUserMessage = hasSubmitted || visibleMessages.some((message) => message.role === 'user')

  function addLocalUserMessage(content: string) {
    if (messages !== undefined) return

    nextMessageNumber.current += 1
    setLocalMessages((current) => [
      ...current,
      {
        id: `${instanceId}-user-${nextMessageNumber.current}`,
        role: 'user',
        content,
      },
    ])
  }

  function finishSubmission(result: void | Promise<void>) {
    if (!isPromise(result)) {
      setInput('')
      pendingRef.current = false
      return
    }

    setPending(true)
    void result
      .then(() => setInput(''))
      .catch((error: unknown) => onError?.(error))
      .finally(() => {
        pendingRef.current = false
        setPending(false)
      })
  }

  function submit(rawMessage: string) {
    const message = rawMessage.trim()
    if (message.length === 0 || pendingRef.current) return

    pendingRef.current = true
    setHasSubmitted(true)
    addLocalUserMessage(message)

    try {
      finishSubmission(onSubmit?.(message))
    } catch (error: unknown) {
      pendingRef.current = false
      onError?.(error)
    }
  }

  return (
    <section className={styles.root} aria-label={`${assistantName} widget`}>
      <div className={styles.header}>
        <p className={styles.title}>{assistantName}</p>
      </div>
      <div
        aria-busy={pending}
        aria-label={`${assistantName} conversation`}
        aria-live="polite"
        aria-relevant="additions text"
        className={styles.conversation}
        role="log"
      >
        <ol className={styles.messages}>
          {visibleMessages.map((message) => (
            <ConversationMessage key={message.id} message={message} />
          ))}
        </ol>
        {!hasUserMessage && (
          <SuggestedFollowUps
            disabled={pending}
            onSelect={submit}
            questions={suggestedQuestions}
          />
        )}
      </div>
      <MessageComposer
        assistantName={assistantName}
        disabled={pending}
        inputId={`${instanceId}-message`}
        onChange={setInput}
        onSubmit={() => submit(input)}
        placeholder={placeholder}
        statusId={`${instanceId}-status`}
        value={input}
      />
      <p
        aria-atomic="true"
        className={styles.visuallyHidden}
        id={`${instanceId}-status`}
        role="status"
      >
        {pending ? 'Sending message' : ''}
      </p>
    </section>
  )
}
