// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { REPLY_SPEEDS } from '@convsim/shared'
import type { ReplySpeed } from '@convsim/shared'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from './ApiErrorView'
import { useTranslation } from '../i18n'

/**
 * "Make the model respond faster", as a thing the app actually offers
 * (issue #501 §1).
 *
 * The playtester went to Settings mid-tutorial to speed the model up and was
 * "a little unclear on how to do that": the only knobs were context length,
 * GPU layers, CPU threads and sampling, all behind a "Show runtime advanced
 * settings" toggle and all written in runtime terms. None of them is named
 * after what they wanted.
 *
 * Three named options, each with a two- or three-word descriptor — the pattern
 * the note asked for ("3 Flash, 3 Pro" paired with "all-around thinking,
 * advanced reasoning"). What they do lives in convsim-core's reply_speed
 * setting; this only has to name them honestly and say what the trade is.
 */
export default function ReplySpeedPanel() {
  const { t } = useTranslation()
  const [speed, setSpeed] = useState<ReplySpeed>('balanced')
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<ApiError | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    const r = await api.getRuntimeSettings()
    if (!r.ok) {
      // A bundled runtime that predates /api/runtime/settings answers 404.
      // RuntimeSettingsPanel already explains that and points at the update, so
      // this control just steps aside rather than stacking a second notice.
      if (r.error.kind === 'http-error' && r.error.status === 404) {
        setUnavailable(true)
        return
      }
      setLoadError(r.error)
      return
    }
    setSpeed(r.data.settings.reply_speed ?? 'balanced')
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function choose(next: ReplySpeed) {
    if (next === speed) return
    const previous = speed
    // Optimistic: the point of this control is that it feels immediate.
    setSpeed(next)
    setSaving(true)
    setSaved(false)
    setSaveError(null)
    const r = await api.updateRuntimeSettings({ reply_speed: next })
    setSaving(false)
    if (!r.ok) {
      setSpeed(previous)
      setSaveError(r.error)
      return
    }
    setSpeed(r.data.settings.reply_speed ?? next)
    setSaved(true)
  }

  if (unavailable) return null
  if (loadError) {
    return <ApiErrorView error={loadError} onRetry={() => void load()} context="ReplySpeedPanel" />
  }

  return (
    <div>
      <div
        role="radiogroup"
        aria-label={t('settings.replySpeed.label')}
        data-testid="reply-speed-options"
        style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.6rem' }}
      >
        {REPLY_SPEEDS.map((option) => {
          const selected = option === speed
          return (
            <button
              key={option}
              role="radio"
              aria-checked={selected}
              data-testid={`reply-speed-${option}`}
              onClick={() => void choose(option)}
              disabled={saving}
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
                cursor: saving ? 'wait' : 'pointer',
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
                {t(`settings.replySpeed.${option}.label`)}
              </span>
              <span style={{ display: 'block', fontSize: '0.78rem', color: '#a1a1aa' }}>
                {t(`settings.replySpeed.${option}.detail`)}
              </span>
            </button>
          )
        })}
      </div>

      <p aria-live="polite" style={{ margin: 0, fontSize: '0.8rem', color: saved ? '#86efac' : '#71717a' }}>
        {saving
          ? t('settings.replySpeed.saving')
          : saved
          ? t('settings.replySpeed.saved')
          : t('settings.replySpeed.noRestart')}
      </p>

      {saveError && (
        <div style={{ marginTop: '0.5rem' }}>
          <ApiErrorView error={saveError} compact context="ReplySpeedPanel-Save" />
        </div>
      )}

      {/* Honest about the ceiling: reply length is the lever this control has,
          and on slow hardware a smaller model is a bigger one. */}
      <p style={{ margin: '0.6rem 0 0', fontSize: '0.8rem', color: '#71717a' }}>
        {t('settings.replySpeed.biggerWin')}{' '}
        <Link to="/model-manager" style={{ color: '#818cf8' }}>
          {t('settings.replySpeed.biggerWinLink')}
        </Link>
      </p>
    </div>
  )
}
