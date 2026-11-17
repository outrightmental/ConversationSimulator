// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ENGINE_VARIANTS } from '@convsim/shared'
import type { EngineStatusResponse, EngineVariant } from '@convsim/shared'
import { api } from '../api/client'
import type { ApiError } from '../api/errors'
import { ApiErrorView } from './ApiErrorView'
import { useTranslation } from '../i18n'

/** Fired on `window` when the engine choice or its failure record changes, so
 *  the one-time notice in the app chrome re-reads instead of lingering. */
export const ENGINE_STATUS_CHANGED_EVENT = 'convsim:engine-status-changed'

type Outcome = 'applied' | 'saved' | 'retryWorked' | 'retryFailed' | 'retryLater' | null

/**
 * Graphics card or processor (issue #531).
 *
 * Says in plain words which part of the computer is writing the replies, lets
 * the player choose (Automatic, the graphics card, or the processor only), and
 * offers "Try the graphics card again" once the app has fallen back from the
 * card. In every edition: the demo's first reply is where the card matters
 * most, and a demo player whose card failed needs the same way back.
 */
export default function GraphicsCardPanel({ header }: { header?: ReactNode }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<EngineStatusResponse | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [busy, setBusy] = useState<'choose' | 'retry' | null>(null)
  const [outcome, setOutcome] = useState<Outcome>(null)
  const [error, setError] = useState<ApiError | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await api.getEngineStatus()
      if (!r.ok) {
        // A core that predates the endpoint answers 404: there is nothing to
        // choose between, so the section says nothing rather than an error.
        if (r.error.kind === 'http-error' && r.error.status === 404) setUnavailable(true)
        else setError(r.error)
        return
      }
      setStatus(r.data)
    } catch {
      setUnavailable(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** Tell the app chrome to re-read. A failure that happened while the player
   *  is looking at this panel is reported here, so it is marked seen: the
   *  player is told once, not twice. */
  async function settle(next: EngineStatusResponse) {
    let latest = next
    if (next.notice_pending) {
      const seen = await api.markEngineNoticeSeen()
      if (seen.ok) latest = seen.data
    }
    setStatus(latest)
    window.dispatchEvent(new CustomEvent(ENGINE_STATUS_CHANGED_EVENT))
  }

  async function choose(next: EngineVariant) {
    // Re-entry guard rather than `disabled`, as in ReplySpeedPanel: disabling
    // the pressed option drops gamepad focus to <body>.
    if (busy || !status || next === status.setting) return
    setBusy('choose')
    setOutcome(null)
    setError(null)
    const saved = await api.updateRuntimeSettings({ engine_variant: next })
    if (!saved.ok) {
      setError(saved.error)
      setBusy(null)
      return
    }
    const wasRunning = status.running !== null
    setStatus({ ...status, setting: next })
    const restarted = await api.restartEngine()
    setBusy(null)
    if (!restarted.ok) {
      setError(restarted.error)
      return
    }
    setOutcome(wasRunning ? 'applied' : 'saved')
    await settle(restarted.data)
  }

  async function retry() {
    if (busy) return
    setBusy('retry')
    setOutcome(null)
    setError(null)
    const r = await api.retryGraphicsCard()
    setBusy(null)
    if (!r.ok) {
      setError(r.error)
      return
    }
    if (r.data.running === 'vulkan') setOutcome('retryWorked')
    else if (r.data.running === null) setOutcome('retryLater')
    else setOutcome('retryFailed')
    await settle(r.data)
  }

  if (unavailable) return null
  if (error && !status) {
    return (
      <section id="graphics-card" style={{ marginBottom: '2rem' }} data-testid="settings-graphics-card-section">
        {header}
        <ApiErrorView error={error} onRetry={() => void load()} context="GraphicsCardPanel" />
      </section>
    )
  }
  if (!status) return null

  const hasCard = status.available.includes('vulkan')
  const statusLine = (() => {
    if (status.running === 'vulkan') {
      return status.device
        ? t('settings.graphicsCard.statusGpu', { device: status.device })
        : t('settings.graphicsCard.statusGpuUnnamed')
    }
    if (status.running === 'metal') return t('settings.graphicsCard.statusMetal')
    if (!hasCard && !status.available.includes('metal')) return t('settings.graphicsCard.processorOnlyBuild')
    if (status.running === null) return t('settings.graphicsCard.statusNotRunning')
    if (status.gpu_failure) return t('settings.graphicsCard.statusCpuAfterFailure')
    if (status.setting === 'auto') return t('settings.graphicsCard.statusCpuNoCard')
    return t('settings.graphicsCard.statusCpu')
  })()

  const message =
    busy === 'choose'
      ? t('settings.graphicsCard.applying')
      : busy === 'retry'
      ? t('settings.graphicsCard.retrying')
      : outcome
      ? t(`settings.graphicsCard.${outcome}`)
      : null

  return (
    <section id="graphics-card" style={{ marginBottom: '2rem' }} data-testid="settings-graphics-card-section">
      {header}
      <p data-testid="graphics-card-status" style={{ margin: '0 0 0.6rem', fontSize: '0.875rem', color: '#d4d4d8' }}>
        {statusLine}
      </p>

      {hasCard && (
        <div
          role="radiogroup"
          aria-label={t('settings.graphicsCard.choiceLabel')}
          aria-busy={busy !== null}
          data-testid="graphics-card-options"
          style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.6rem' }}
        >
          {ENGINE_VARIANTS.map((option) => {
            const selected = option === status.setting
            return (
              <button
                key={option}
                role="radio"
                aria-checked={selected}
                data-testid={`graphics-card-${option}`}
                onClick={() => void choose(option)}
                style={{
                  flex: '1 1 10rem',
                  textAlign: 'left',
                  padding: '0.55rem 0.75rem',
                  borderRadius: '6px',
                  border: selected ? '1px solid rgba(99,102,241,0.7)' : '1px solid rgba(255,255,255,0.12)',
                  background: selected ? 'rgba(99,102,241,0.15)' : 'transparent',
                  color: 'inherit',
                  cursor: busy ? 'wait' : 'pointer',
                  font: 'inherit',
                }}
              >
                <span style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', color: selected ? '#c7d2fe' : '#e8e8ea' }}>
                  {t(`settings.graphicsCard.${option}.label`)}
                </span>
                <span style={{ display: 'block', fontSize: '0.78rem', color: '#a1a1aa' }}>
                  {t(`settings.graphicsCard.${option}.detail`)}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {hasCard && status.gpu_failure && status.setting !== 'cpu' && (
        <button
          data-testid="graphics-card-retry"
          onClick={() => void retry()}
          style={{
            padding: '0.35rem 0.9rem',
            borderRadius: '4px',
            border: '1px solid rgba(99,102,241,0.4)',
            background: 'rgba(99,102,241,0.2)',
            color: '#a5b4fc',
            cursor: busy ? 'wait' : 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            marginBottom: '0.5rem',
          }}
        >
          {t('settings.graphicsCard.retry')}
        </button>
      )}

      {message && (
        <p aria-live="polite" style={{ margin: 0, fontSize: '0.8rem', color: outcome === 'retryFailed' ? '#fbbf24' : '#86efac' }}>
          {message}
        </p>
      )}

      {error && (
        <div style={{ marginTop: '0.5rem' }}>
          <ApiErrorView error={error} compact context="GraphicsCardPanel-Action" />
        </div>
      )}
    </section>
  )
}
