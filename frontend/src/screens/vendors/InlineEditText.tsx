import { useRef, useState } from "react"

interface InlineEditTextProps {
  value: string
  onSubmit: (next: string) => Promise<void> | void
  ariaLabel: string
  multiline?: boolean
  placeholder?: string
  error?: string | null
  onEditStart?: () => void
  displayClassName?: string
  inputClassName?: string
  readOnly?: boolean
}

/**
 * Инлайн-правка текста (Notion/Linear): клик по дисплею → поле на месте.
 * single: Enter/blur сохраняют, Esc отменяет; multiline: blur сохраняет, Esc
 * отменяет (Enter — перенос строки). No-op (draft==value) и single+пусто не
 * зовут onSubmit. Reject onSubmit → остаёмся в правке (ошибку рисует родитель
 * через `error`). doneRef гарантирует один commit на сессию (Enter+последующий
 * blur не дают двойного сохранения).
 */
export function InlineEditText({
  value,
  onSubmit,
  ariaLabel,
  multiline = false,
  placeholder,
  error,
  onEditStart,
  displayClassName,
  inputClassName,
  readOnly = false,
}: InlineEditTextProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const doneRef = useRef(false)

  function startEdit() {
    doneRef.current = false
    setDraft(value)
    onEditStart?.()
    setEditing(true)
  }

  async function commit() {
    if (doneRef.current) return
    const next = draft.trim()
    if (next === value.trim() || (!multiline && next === "")) {
      doneRef.current = true
      setEditing(false)
      return
    }
    doneRef.current = true
    setSaving(true)
    try {
      await onSubmit(multiline ? draft : next)
      setEditing(false)
    } catch {
      doneRef.current = false // разрешаем повтор; остаёмся в правке
    } finally {
      setSaving(false)
    }
  }

  function cancel() {
    doneRef.current = true
    setEditing(false)
  }

  if (readOnly) {
    const empty = value.trim() === ""
    if (empty) return null // в view пустое примечание не занимает место
    return <span className={displayClassName}>{value}</span>
  }
  if (!editing) {
    const empty = value.trim() === ""
    return (
      <button
        type="button"
        onClick={startEdit}
        aria-label={ariaLabel}
        className={displayClassName}
      >
        {empty ? (placeholder ?? "") : value}
      </button>
    )
  }

  const shared = {
    autoFocus: true,
    value: draft,
    disabled: saving,
    "aria-label": ariaLabel,
    "aria-invalid": error ? true : undefined,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setDraft(e.target.value),
    onBlur: () => {
      void commit()
    },
    className: inputClassName,
  }

  return (
    <span className="inline-flex flex-col">
      {multiline ? (
        <textarea
          {...shared}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
          }}
        />
      ) : (
        <input
          {...shared}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              void commit()
            } else if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
          }}
        />
      )}
      {error && (
        <span role="alert" className="mt-1 text-caption text-destructive">
          {error}
        </span>
      )}
    </span>
  )
}
