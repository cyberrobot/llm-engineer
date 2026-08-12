import styles from './AssistantWidget.module.css'

interface SuggestedFollowUpsProps {
  disabled: boolean
  questions: readonly string[]
  onSelect: (question: string) => void
}

export function SuggestedFollowUps({
  disabled,
  questions,
  onSelect,
}: SuggestedFollowUpsProps) {
  if (questions.length === 0) return null

  return (
    <div className={styles.suggestions} role="group" aria-label="Suggested questions">
      <p className={styles.suggestionsLabel}>You might ask</p>
      <div className={styles.suggestionList}>
        {questions.map((question, index) => (
          <button
            className={styles.suggestion}
            disabled={disabled}
            key={`${index}-${question}`}
            onClick={() => onSelect(question)}
            type="button"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}
