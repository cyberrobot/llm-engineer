import type { AssistantMessage } from './AssistantWidget.types'
import styles from './AssistantWidget.module.css'

interface ConversationMessageProps {
  message: AssistantMessage
}

export function ConversationMessage({ message }: ConversationMessageProps) {
  return (
    <li className={`${styles.message} ${styles[message.role]}`}>
      <span className={styles.messageRole}>{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
      <p className={styles.messageContent}>{message.content}</p>
    </li>
  )
}
