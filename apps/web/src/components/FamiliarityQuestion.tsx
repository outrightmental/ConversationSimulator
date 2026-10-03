// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useTranslation } from '../i18n'
import {
  readLlmFamiliarity,
  writeLlmFamiliarity,
  type LlmFamiliarity,
} from '../lib/plainLanguage'

const ANSWERS: LlmFamiliarity[] = ['new', 'some', 'expert']

/**
 * "How familiar are you with AI language models?" (issue #501 §2).
 *
 * The note asked for the wording buffer to be "chosen by an initial LLM
 * familiarity question", so this is a question about the player rather than a
 * setting about the app: nobody arriving for the first time knows whether they
 * want "technical wording", but everyone knows whether they work with language
 * models.
 *
 * Deliberately not a wizard step and never blocking. Answering is one click,
 * skipping it is free, and the unanswered default is plain wording — the safe
 * direction, since Settings is one click away and a first session reading
 * `PlayerTurnListening` is not recoverable.
 */
export default function FamiliarityQuestion({
  heading,
  onAnswered,
  compact = false,
}: {
  /** Which phrasing to use — first run, or the post-tutorial re-ask. */
  heading: string
  onAnswered?: (answer: LlmFamiliarity) => void
  compact?: boolean
}) {
  const { t } = useTranslation()
  // Held in state, not read fresh from storage each render: on the first-run
  // Welcome step nothing else re-renders when an answer is written, so a
  // storage-only read left every option unselected after the click — the
  // player tells the app how familiar they are and the app appears to ignore
  // them.
  const [current, setCurrent] = useState<LlmFamiliarity | null>(readLlmFamiliarity)

  return (
    <div data-testid="familiarity-question">
      <p
        style={{
          margin: '0 0 0.5rem',
          fontSize: compact ? '0.875rem' : '0.95rem',
          color: '#e4e4e7',
          fontWeight: 600,
        }}
      >
        {heading}
      </p>
      <div
        role="radiogroup"
        aria-label={heading}
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}
      >
        {ANSWERS.map((answer) => {
          const selected = answer === current
          return (
            <button
              key={answer}
              role="radio"
              aria-checked={selected}
              data-testid={`familiarity-${answer}`}
              onClick={() => {
                writeLlmFamiliarity(answer)
                setCurrent(answer)
                onAnswered?.(answer)
              }}
              style={{
                flex: '1 1 9rem',
                textAlign: 'left',
                padding: '0.5rem 0.7rem',
                borderRadius: '6px',
                border: selected
                  ? '1px solid rgba(99,102,241,0.7)'
                  : '1px solid rgba(255,255,255,0.12)',
                background: selected ? 'rgba(99,102,241,0.15)' : 'transparent',
                color: 'inherit',
                cursor: 'pointer',
                font: 'inherit',
              }}
            >
              <span style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem' }}>
                {t(`familiarity.${answer}.label`)}
              </span>
              <span style={{ display: 'block', fontSize: '0.75rem', color: '#a1a1aa' }}>
                {t(`familiarity.${answer}.detail`)}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
