import type { FormEvent, KeyboardEvent } from 'react'

import styles from './AssistantWidget.module.css'

export const MAX_MESSAGE_LENGTH = 2_000

interface MessageComposerProps {
  assistantName: string
  disabled: boolean
  inputId: string
  placeholder: string
  statusId: string
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
}

export function MessageComposer({
  assistantName,
  disabled,
  inputId,
  placeholder,
  statusId,
  value,
  onChange,
  onSubmit,
}: MessageComposerProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return

    event.preventDefault()
    onSubmit()
  }

  return (
    <form className={styles.composer} onSubmit={handleSubmit}>
      <label className={styles.visuallyHidden} htmlFor={inputId}>
        Ask {assistantName} a question
      </label>
      <textarea
        aria-describedby={statusId}
        autoComplete="off"
        className={styles.input}
        disabled={disabled}
        id={inputId}
        maxLength={MAX_MESSAGE_LENGTH}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        value={value}
      />
      <button className={styles.submit} disabled={disabled || value.trim().length === 0} type="submit">
        Send<span className={styles.visuallyHidden}> message</span>
      </button>
    </form>
  )
}
