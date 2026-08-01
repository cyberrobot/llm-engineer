import type { StatefulConversationMessage } from './conversationHistory'
import styles from './AssistantWidget.module.css'

interface ConversationMessageProps {
  message: StatefulConversationMessage
}

export function ConversationMessage({ message }: ConversationMessageProps) {
  return (
    <li className={`${styles.message} ${styles[message.role]}`}>
      <span className={styles.messageRole}>{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
      <p className={styles.messageContent}>{message.content}</p>
    </li>
  )
}
