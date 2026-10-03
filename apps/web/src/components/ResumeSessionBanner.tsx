// SPDX-License-Identifier: Apache-2.0
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { useTranslation } from '../i18n'
import { useResumableSession } from '../hooks/useResumableSession'
import { useScenarios } from '../api/useScenarios'

/**
 * "You have a conversation in progress — Resume" (issue #501 §1).
 *
 * Lives in the app chrome rather than on Home, because the screen the player
 * got lost on was Settings: they went there to speed the model up and then
 * could not find the way back. A strip under the header is on every screen the
 * detour can reach, so there is always one click back into the conversation.
 *
 * Hidden on the conversation itself (you are already there), on the debrief for
 * that session (you have left it on purpose), and during first-run setup.
 */
export default function ResumeSessionBanner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const scenarios = useScenarios()

  // Nothing to resume *to* while the player is mid-conversation or reading the
  // debrief, so do not spend a request asking.
  const onConversationRoute =
    location.pathname.startsWith('/conversation/') ||
    location.pathname.startsWith('/debrief/')
  const { result, refetch } = useResumableSession(!onConversationRoute)

  if (result.state !== 'ready') return null

  const session = result.session
  const title =
    scenarios.scenarios.find((s) => s.scenario_id === session.scenario_id)?.title ??
    session.scenario_id
  const turns = session.turn_count ?? 0

  function handleResume() {
    navigate(`/conversation/${session.session_id}`)
  }

  async function handleEnd() {
    const r = await api.endSession(session.session_id)
    // Either way the banner has to re-ask: on success the session is no longer
    // resumable, and on failure the row may have been ended by another window.
    void r
    refetch()
  }

  return (
    <div
      role="status"
      data-testid="resume-session-banner"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        flexWrap: 'wrap',
        padding: '0.5rem 1.5rem',
        background: 'rgba(99,102,241,0.12)',
        borderBottom: '1px solid rgba(99,102,241,0.35)',
        fontSize: '0.875rem',
      }}
    >
      <span style={{ color: '#c7d2fe', flex: 1, minWidth: '12rem' }}>
        <strong style={{ fontWeight: 600 }}>{t('resume.label')}</strong>{' '}
        {turns > 0
          ? t('resume.withTurns', { title, count: turns })
          : t('resume.withoutTurns', { title })}
      </span>
      <button
        onClick={handleResume}
        data-testid="resume-session-button"
        style={{
          padding: '0.3rem 0.9rem',
          borderRadius: '4px',
          border: 'none',
          background: '#4f46e5',
          color: '#fff',
          fontWeight: 600,
          fontSize: '0.8rem',
          cursor: 'pointer',
        }}
      >
        {t('resume.action')}
      </button>
      <button
        onClick={() => void handleEnd()}
        data-testid="resume-session-end-button"
        style={{
          padding: '0.3rem 0.75rem',
          borderRadius: '4px',
          border: '1px solid rgba(255,255,255,0.2)',
          background: 'transparent',
          color: '#a1a1aa',
          fontSize: '0.8rem',
          cursor: 'pointer',
        }}
      >
        {t('resume.dismiss')}
      </button>
    </div>
  )
}
