// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useTranslation } from '../../i18n'
import { ActionButton } from '../primitives'
import type { UseSetupFlowReturn } from '../useSetupFlow'

const SETUP_DOCS_URL = 'https://docs.conversationsimulator.com/start/install/'

const cardBase: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
  borderRadius: '10px', padding: '1.25rem', cursor: 'pointer',
  color: 'inherit', textAlign: 'left', fontFamily: 'inherit', fontSize: 'inherit',
  width: '100%',
}

export function WelcomeStep({ flow }: { flow: UseSetupFlowReturn }) {
  const { t } = useTranslation()
  const rec = flow.recommendedModel
  const [privacyOpen, setPrivacyOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  return (
    <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none', marginBottom: '0.25rem' }}>
        {t('setup.welcome.headline')}
      </h1>
      <p style={{ margin: '0 0 2rem', color: '#a1a1aa', fontSize: '1.1rem' }}>
        {t('setup.welcome.subheadline')}
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Set me up card */}
        <button
          onClick={() => flow.handleSetMeUp()}
          disabled={flow.actionLoading}
          style={{
            ...cardBase,
            background: 'rgba(99,102,241,0.1)',
            border: '2px solid rgba(99,102,241,0.5)',
          }}
        >
          <span aria-hidden="true" style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>✨</span>
          <strong style={{ display: 'block', fontSize: '1.05rem', marginBottom: '0.5rem' }}>
            {t('setup.welcome.setMeUp.title')}
          </strong>
          <span style={{ display: 'block', fontSize: '0.875rem', color: '#c7d2fe', marginBottom: '0.75rem', lineHeight: 1.5 }}>
            {rec != null
              ? t('setup.welcome.setMeUp.description', { size: rec.size_gb ?? 0, license: rec.license_spdx ?? '' })
              : t('setup.welcome.setMeUp.descriptionLoading')}
          </span>
          <span style={{
            fontSize: '0.75rem', fontWeight: 600, color: '#6ee7b7',
            border: '1px solid rgba(110,231,183,0.5)', borderRadius: '4px', padding: '0.15rem 0.4rem',
          }}>
            {t('setup.welcome.setMeUp.badge')}
          </span>
        </button>

        {/* Try it right now card */}
        <button
          onClick={() => void flow.handleConfirmDemo(true)}
          disabled={flow.actionLoading}
          style={{
            ...cardBase,
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.15)',
          }}
        >
          <span aria-hidden="true" style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⚡</span>
          <strong style={{ display: 'block', fontSize: '1.05rem', marginBottom: '0.5rem' }}>
            {t('setup.welcome.tryNow.title')}
          </strong>
          <span style={{ display: 'block', fontSize: '0.875rem', color: '#a1a1aa', marginBottom: '0.5rem', lineHeight: 1.5 }}>
            {t('setup.welcome.tryNow.description')}
          </span>
          <span style={{ display: 'block', fontSize: '0.8rem', color: '#71717a' }}>
            {t('setup.welcome.tryNow.disclaimer')}
          </span>
        </button>
      </div>

      {/* Privacy disclosure */}
      <div style={{ marginBottom: '0.75rem' }}>
        <button
          onClick={() => setPrivacyOpen((v) => !v)}
          aria-expanded={privacyOpen}
          aria-controls="welcome-privacy-details"
          style={{
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontSize: '0.875rem', color: '#a1a1aa', fontFamily: 'inherit',
          }}
        >
          {t('setup.welcome.privacy.summary')}{' '}
          <span style={{ color: '#71717a' }}>
            {t('setup.welcome.privacy.toggle')} {privacyOpen ? '▴' : '▸'}
          </span>
        </button>
        {privacyOpen && (
          <div
            id="welcome-privacy-details"
            role="note"
            aria-label="privacy details"
            style={{
              marginTop: '0.5rem', padding: '0.75rem 1rem',
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)',
              borderRadius: '6px', fontSize: '0.875rem', color: '#c7d2fe', lineHeight: 1.6,
            }}
          >
            {t('setup.welcome.privacy.details')}
          </div>
        )}
      </div>

      {/* Advanced paths disclosure */}
      <div style={{ marginBottom: '1.25rem' }}>
        <button
          onClick={() => setAdvancedOpen((v) => !v)}
          aria-expanded={advancedOpen}
          aria-controls="welcome-advanced-options"
          style={{
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontSize: '0.875rem', color: '#71717a', fontFamily: 'inherit',
          }}
        >
          {t('setup.welcome.advanced.toggle')} {advancedOpen ? '▴' : '▸'}
        </button>
        {advancedOpen && (
          <div
            id="welcome-advanced-options"
            style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
          >
            <div style={{ padding: '0.75rem 1rem', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
                {t('setup.welcome.advanced.ollama.why')}
              </p>
              <ActionButton onClick={() => flow.handleAdvancedOllama()}>
                {t('setup.welcome.advanced.ollama.action')}
              </ActionButton>
            </div>
            <div style={{ padding: '0.75rem 1rem', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}>
              <p style={{ margin: '0 0 0.5rem', fontSize: '0.875rem', color: '#a1a1aa' }}>
                {t('setup.welcome.advanced.gguf.why')}
              </p>
              <ActionButton
                onClick={() => {
                  flow.setGgufPath('')
                  flow.setGgufPathError(null)
                  flow.resetAction()
                  flow.setStep('gguf-path')
                }}
              >
                {t('setup.welcome.advanced.gguf.action')}
              </ActionButton>
            </div>
          </div>
        )}
      </div>

      <a
        href={SETUP_DOCS_URL}
        target="_blank"
        rel="noreferrer"
        style={{ fontSize: '0.825rem', color: '#71717a' }}
      >
        Read setup docs
      </a>
    </div>
  )
}
