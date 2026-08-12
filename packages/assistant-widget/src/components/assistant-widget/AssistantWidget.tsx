import { useEffect, useId, useRef, useState } from 'react'

import {
  AssistantChatError,
  type AssistantChatErrorCode,
  type AssistantMessage,
  type AssistantWidgetProps,
} from './AssistantWidget.types'
import styles from './AssistantWidget.module.css'
import { ConversationMessage } from './ConversationMessage'
import {
  buildConversationHistory,
  type StatefulConversationMessage,
} from './conversationHistory'
import { MAX_MESSAGE_LENGTH, MessageComposer } from './MessageComposer'
import { SuggestedFollowUps } from './SuggestedFollowUps'

const DEFAULT_ASSISTANT_NAME = 'Assistant'
const DEFAULT_WELCOME_MESSAGE = 'How can I help you today?'
const DEFAULT_PLACEHOLDER = 'Ask a question…'
const clientKeys = new WeakMap<object, number>()
let nextClientKey = 0

interface FailedTurn {
  messageId: string
  code: AssistantChatErrorCode
  retryable: boolean
}

function isPromise(value: void | Promise<void>): value is Promise<void> {
  return value !== undefined && typeof value.then === 'function'
}

function failureFrom(error: unknown): Omit<FailedTurn, 'messageId'> {
  if (error instanceof AssistantChatError) {
    return { code: error.code, retryable: error.retryable }
  }
  return { code: 'server_error', retryable: true }
}

function errorMessage(code: AssistantChatErrorCode): string {
  switch (code) {
    case 'assistant_unavailable':
      return 'This assistant is currently unavailable.'
    case 'rate_limited':
      return 'The assistant is receiving too many requests. Please try again shortly.'
    case 'invalid_request':
      return 'This question could not be sent. Please check it and try again.'
    case 'network_error':
      return "We couldn't reach the assistant. Please check your connection and try again."
    case 'invalid_response':
    case 'server_error':
      return 'Something went wrong while getting a response. Please try again.'
  }
}

function initialMessages(instanceId: string, welcomeMessage: string): StatefulConversationMessage[] {
  return [
    {
      id: `${instanceId}-welcome`,
      role: 'assistant',
      content: welcomeMessage,
      status: 'complete',
      presentationOnly: true,
    },
  ]
}

function asStatefulMessages(messages: readonly AssistantMessage[]): StatefulConversationMessage[] {
  return messages.map((message) => ({ ...message, status: 'complete' }))
}

function clientKey(client: object | undefined): string {
  if (!client) return 'legacy'
  const existing = clientKeys.get(client)
  if (existing !== undefined) return String(existing)
  nextClientKey += 1
  clientKeys.set(client, nextClientKey)
  return String(nextClientKey)
}

function Conversation({
  assistantName = DEFAULT_ASSISTANT_NAME,
  welcomeMessage = DEFAULT_WELCOME_MESSAGE,
  placeholder = DEFAULT_PLACEHOLDER,
  suggestedQuestions = [],
  messages,
  chatClient,
  onSubmit,
  onError,
}: AssistantWidgetProps) {
  const instanceId = useId()
  const nextMessageNumber = useRef(0)
  const pendingRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const conversationRef = useRef<HTMLDivElement>(null)
  const shouldAutoScrollRef = useRef(true)
  const forceScrollRef = useRef(false)
  const [input, setInput] = useState('')
  const [validationError, setValidationError] = useState<string>()
  const [pending, setPending] = useState(false)
  const [hasSubmitted, setHasSubmitted] = useState(false)
  const [failedTurn, setFailedTurn] = useState<FailedTurn>()
  const [localMessages, setLocalMessages] = useState<readonly StatefulConversationMessage[]>(() =>
    initialMessages(instanceId, welcomeMessage),
  )
  const visibleMessages = messages ? asStatefulMessages(messages) : localMessages
  const hasUserMessage = hasSubmitted || visibleMessages.some((message) => message.role === 'user')

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  useEffect(() => {
    const conversation = conversationRef.current
    if (!conversation || (!forceScrollRef.current && !shouldAutoScrollRef.current)) return
    conversation.scrollTop = conversation.scrollHeight
    forceScrollRef.current = false
  }, [failedTurn, localMessages, pending])

  function nextId(role: 'user' | 'assistant') {
    nextMessageNumber.current += 1
    return `${instanceId}-${role}-${nextMessageNumber.current}`
  }

  function restoreComposer() {
    pendingRef.current = false
    setPending(false)
    window.setTimeout(() => composerRef.current?.focus(), 0)
  }

  async function requestAnswer(
    userMessage: StatefulConversationMessage,
    precedingMessages: readonly StatefulConversationMessage[],
  ) {
    if (!chatClient) return

    const controller = new AbortController()
    abortRef.current?.abort()
    abortRef.current = controller
    setPending(true)
    setFailedTurn(undefined)
    const assistantMessageId = nextId('assistant')
    let streamedAnswer = ''

    try {
      const request = {
        message: userMessage.content,
        history: buildConversationHistory(
          precedingMessages,
          chatClient.historyLimit,
          userMessage.id,
        ),
      }
      const response = chatClient.stream
        ? await chatClient.stream(request, {
            signal: controller.signal,
            onDelta(delta) {
              if (controller.signal.aborted) return
              streamedAnswer += delta
              const nextAnswer = streamedAnswer
              setLocalMessages((current) => {
                if (controller.signal.aborted) return current
                const existing = current.some((message) => message.id === assistantMessageId)
                if (!existing) {
                  return [
                    ...current,
                    {
                      id: assistantMessageId,
                      role: 'assistant',
                      content: nextAnswer,
                      status: 'pending',
                    },
                  ]
                }
                return current.map((message) =>
                  message.id === assistantMessageId
                    ? { ...message, content: nextAnswer }
                    : message,
                )
              })
            },
          })
        : await chatClient.send(request, { signal: controller.signal })
      if (controller.signal.aborted) return
      if (typeof response.answer !== 'string' || response.answer.trim().length === 0) {
        throw new AssistantChatError('invalid_response', true)
      }
      if (chatClient.stream && streamedAnswer !== response.answer) {
        throw new AssistantChatError('invalid_response', true)
      }

      setLocalMessages((current) => {
        const completedMessages = current.map((message) => {
          if (message.id === userMessage.id) return { ...message, status: 'complete' as const }
          if (message.id === assistantMessageId) {
            return { ...message, content: response.answer, status: 'complete' as const }
          }
          return message
        })
        if (current.some((message) => message.id === assistantMessageId)) return completedMessages
        return [
          ...completedMessages,
          {
            id: assistantMessageId,
            role: 'assistant',
            content: response.answer,
            status: 'complete',
          },
        ]
      })
    } catch (error: unknown) {
      if (controller.signal.aborted) return
      const failure = failureFrom(error)
      setLocalMessages((current) =>
        current
          .filter((message) => message.id !== assistantMessageId)
          .map((message) =>
            message.id === userMessage.id ? { ...message, status: 'failed' } : message,
          ),
      )
      setFailedTurn({ messageId: userMessage.id, ...failure })
      onError?.(error)
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      if (!controller.signal.aborted) restoreComposer()
    }
  }

  function finishLegacySubmission(result: void | Promise<void>) {
    if (!isPromise(result)) {
      setInput('')
      pendingRef.current = false
      return
    }

    setPending(true)
    void result
      .then(() => setInput(''))
      .catch((error: unknown) => onError?.(error))
      .finally(restoreComposer)
  }

  function submit(rawMessage: string) {
    const message = rawMessage.trim()
    if (message.length === 0 || pendingRef.current) return
    if (message.length > MAX_MESSAGE_LENGTH) {
      setValidationError(`Questions must be ${MAX_MESSAGE_LENGTH} characters or fewer.`)
      return
    }

    pendingRef.current = true
    setValidationError(undefined)
    setHasSubmitted(true)
    forceScrollRef.current = true

    if (chatClient && messages === undefined) {
      const userMessage: StatefulConversationMessage = {
        id: nextId('user'),
        role: 'user',
        content: message,
        status: 'pending',
      }
      const precedingMessages = localMessages
      setLocalMessages((current) => [...current, userMessage])
      setInput('')
      void requestAnswer(userMessage, precedingMessages)
      return
    }

    if (messages === undefined) {
      setLocalMessages((current) => [
        ...current,
        { id: nextId('user'), role: 'user', content: message, status: 'complete' },
      ])
    }

    try {
      finishLegacySubmission(onSubmit?.(message))
    } catch (error: unknown) {
      pendingRef.current = false
      onError?.(error)
    }
  }

  function retry() {
    if (!failedTurn?.retryable || pendingRef.current || messages !== undefined) return
    const index = localMessages.findIndex((message) => message.id === failedTurn.messageId)
    const userMessage = localMessages[index]
    if (!userMessage) return

    pendingRef.current = true
    setLocalMessages((current) =>
      current.map((message) =>
        message.id === failedTurn.messageId ? { ...message, status: 'pending' } : message,
      ),
    )
    void requestAnswer({ ...userMessage, status: 'pending' }, localMessages.slice(0, index))
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
        onScroll={(event) => {
          const conversation = event.currentTarget
          shouldAutoScrollRef.current =
            conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight <= 80
        }}
        ref={conversationRef}
        role="log"
      >
        <ol className={styles.messages}>
          {visibleMessages.map((message) => (
            <ConversationMessage key={message.id} message={message} />
          ))}
        </ol>
        {pending && chatClient && (
          <p className={styles.pending}>Thinking…</p>
        )}
        {failedTurn && (
          <div className={styles.failure} role="alert">
            <p>{errorMessage(failedTurn.code)}</p>
            {failedTurn.retryable && (
              <button className={styles.retry} disabled={pending} onClick={retry} type="button">
                Retry question
              </button>
            )}
          </div>
        )}
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
        error={validationError}
        inputId={`${instanceId}-message`}
        inputRef={composerRef}
        onChange={(value) => {
          setInput(value)
          if (validationError) setValidationError(undefined)
        }}
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
        {pending ? (chatClient ? 'Waiting for assistant response' : 'Sending message') : ''}
      </p>
    </section>
  )
}

export function AssistantWidgetConversation(props: AssistantWidgetProps) {
  const configurationKey = `${clientKey(props.chatClient)}:${props.welcomeMessage ?? DEFAULT_WELCOME_MESSAGE}`
  return <Conversation key={configurationKey} {...props} />
}
