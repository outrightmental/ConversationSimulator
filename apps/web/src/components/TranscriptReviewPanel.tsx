// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, useRef } from 'react'

export interface TranscriptReviewPanelProps {
  transcript: string
  language?: string | null
  confidence?: number | null
  onConfirm: (text: string) => void
  onCancel: () => void
  onRetry: () => void
}

export default function TranscriptReviewPanel({
  transcript,
  language,
  confidence,
  onConfirm,
  onCancel,
  onRetry,
}: TranscriptReviewPanelProps) {
  const [editedText, setEditedText] = useState(transcript)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, [])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      const trimmed = editedText.trim()
      if (trimmed) onConfirm(trimmed)
    }
  }

  const trimmed = editedText.trim()

  return (
    <div
      role="region"
      aria-label="Transcript review"
      data-testid="transcript-review-panel"
      style={panelStyle}
    >
      <div style={headerStyle}>
        <span style={labelStyle}>Review speech transcript</span>
        {(language || confidence != null) && (
          <span style={hintsStyle} data-testid="transcript-hints">
            {language && <span>Language: {language}</span>}
            {confidence != null && (
              <span style={language ? { marginLeft: 8 } : undefined}>
                Confidence: {Math.round(confidence * 100)}%
              </span>
            )}
          </span>
        )}
      </div>

      <textarea
        ref={textareaRef}
        value={editedText}
        onChange={(e) => setEditedText(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Edit transcript"
        rows={3}
        style={textareaStyle}
      />

      <div style={actionsStyle}>
        <button
          type="button"
          onClick={() => { if (trimmed) onConfirm(trimmed) }}
          disabled={!trimmed}
          aria-label="Submit transcript"
          style={{ ...buttonBase, background: '#2563eb', color: '#fff', fontWeight: 600 }}
        >
          Submit
        </button>
        <button
          type="button"
          onClick={onRetry}
          aria-label="Retry recording"
          style={{ ...buttonBase, background: '#27272a', color: '#a1a1aa', border: '1px solid #3f3f46' }}
        >
          Retry
        </button>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Cancel and discard transcript"
          style={{ ...buttonBase, background: 'transparent', color: '#71717a', border: '1px solid #3f3f46' }}
        >
          Cancel
        </button>
        <span style={kbdHintStyle}>
          <kbd style={kbdStyle}>Ctrl+Enter</kbd> submit &nbsp;
          <kbd style={kbdStyle}>Esc</kbd> cancel
        </span>
      </div>
    </div>
  )
}

const panelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.5rem',
  padding: '0.75rem',
  borderRadius: 8,
  border: '1px solid #3f3f46',
  background: '#18181b',
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: '0.25rem',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.8rem',
  color: '#a78bfa',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

const hintsStyle: React.CSSProperties = {
  fontSize: '0.75rem',
  color: '#71717a',
}

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '0.5rem 0.75rem',
  borderRadius: 6,
  border: '1px solid #3f3f46',
  background: '#09090b',
  color: '#e4e4e7',
  fontSize: '0.95rem',
  resize: 'vertical',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
}

const actionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: '0.5rem',
  alignItems: 'center',
  flexWrap: 'wrap',
}

const buttonBase: React.CSSProperties = {
  padding: '0.4rem 0.9rem',
  borderRadius: 6,
  border: 'none',
  cursor: 'pointer',
  fontSize: '0.875rem',
}

const kbdHintStyle: React.CSSProperties = {
  marginLeft: 'auto',
  fontSize: '0.75rem',
  color: '#52525b',
}

const kbdStyle: React.CSSProperties = {
  padding: '0.1rem 0.3rem',
  borderRadius: 3,
  border: '1px solid #52525b',
  fontFamily: 'monospace',
  fontSize: '0.7rem',
  background: '#27272a',
}
