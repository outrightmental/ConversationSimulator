// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from '../i18n'
import { useUiLanguageLevel } from '../hooks/useUiLanguageLevel'
import type { UiLanguageLevel } from '../lib/plainLanguage'

const LEVELS: UiLanguageLevel[] = ['plain', 'technical']

/**
 * The "deliberately peek into the settings" half of issue #501 §2.
 *
 * The familiarity question sets this on first run and offers to revisit it
 * after the tutorial; this is where it lives permanently, so a player who
 * answered "new to this" and then wanted the session id for a bug report is
 * one switch away from it.
 */
export default function WordingPanel() {
  const { t } = useTranslation()
  const { level, setLevel } = useUiLanguageLevel()

  return (
    <div
      role="radiogroup"
      aria-label={t('settings.wording.heading')}
      data-testid="wording-options"
      style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}
    >
      {LEVELS.map((option) => {
        const selected = option === level
        return (
          <button
            key={option}
            role="radio"
            aria-checked={selected}
            data-testid={`wording-${option}`}
            onClick={() => setLevel(option)}
            style={{
              flex: '1 1 10rem',
              textAlign: 'left',
              padding: '0.55rem 0.75rem',
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
            <span
              style={{
                display: 'block',
                fontWeight: 600,
                fontSize: '0.875rem',
                color: selected ? '#c7d2fe' : '#e8e8ea',
              }}
            >
              {t(`settings.wording.${option}.label`)}
            </span>
            <span style={{ display: 'block', fontSize: '0.78rem', color: '#a1a1aa' }}>
              {t(`settings.wording.${option}.detail`)}
            </span>
          </button>
        )
      })}
    </div>
  )
}
