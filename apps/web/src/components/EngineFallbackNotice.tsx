// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useTranslation } from '../i18n'
import { ENGINE_STATUS_CHANGED_EVENT } from './GraphicsCardPanel'

/** How often the chrome re-asks while nothing is pending: a fallback can
 *  happen at any engine start, including mid-conversation. */
const POLL_MS = 30_000

/**
 * "Your graphics card stopped working with the app" — said once (issue #531).
 *
 * The core stores a graphics-card failure with a flag the player has not yet
 * seen; this strip shows it on every screen until the player opens Settings
 * or dismisses it, and either marks it seen, so it never comes back for the
 * same failure. Renders nothing otherwise, and nothing at all when the core
 * cannot be asked.
 */
export default function EngineFallbackNotice() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [pending, setPending] = useState(false)

  const check = useCallback(async () => {
    try {
      const r = await api.getEngineStatus()
      setPending(r.ok && r.data.notice_pending)
    } catch {
      setPending(false)
    }
  }, [])

  useEffect(() => {
    void check()
    const timer = window.setInterval(() => void check(), POLL_MS)
    window.addEventListener(ENGINE_STATUS_CHANGED_EVENT, check)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener(ENGINE_STATUS_CHANGED_EVENT, check)
    }
  }, [check])

  if (!pending) return null

  async function acknowledge() {
    setPending(false)
    try {
      await api.markEngineNoticeSeen()
    } catch {
      // Nothing to do: the strip is gone for this session either way.
    }
  }

  async function openSettings() {
    await acknowledge()
    if (location.pathname !== '/settings') navigate('/settings#graphics-card')
  }

  return (
    <div
      role="status"
      data-testid="engine-fallback-notice"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        flexWrap: 'wrap',
        padding: '0.5rem 1.5rem',
        background: 'rgba(251,191,36,0.10)',
        borderBottom: '1px solid rgba(251,191,36,0.35)',
        fontSize: '0.875rem',
      }}
    >
      <span style={{ color: '#fde68a', flex: 1, minWidth: '12rem' }}>{t('engineNotice.message')}</span>
      <button
        data-testid="engine-fallback-open-settings"
        onClick={() => void openSettings()}
        style={{
          padding: '0.3rem 0.8rem',
          borderRadius: '4px',
          border: '1px solid rgba(251,191,36,0.5)',
          background: 'rgba(251,191,36,0.15)',
          color: '#fde68a',
          cursor: 'pointer',
          font: 'inherit',
        }}
      >
        {t('engineNotice.openSettings')}
      </button>
      <button
        data-testid="engine-fallback-dismiss"
        onClick={() => void acknowledge()}
        style={{
          padding: '0.3rem 0.8rem',
          borderRadius: '4px',
          border: '1px solid rgba(255,255,255,0.15)',
          background: 'transparent',
          color: '#e8e8ea',
          cursor: 'pointer',
          font: 'inherit',
        }}
      >
        {t('engineNotice.dismiss')}
      </button>
    </div>
  )
}
