// SPDX-License-Identifier: Apache-2.0
import { ActionButton } from '../primitives'
import { BLOCKING_CHECK_IDS } from '../useSetupFlow'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import { openExternal } from '../../lib/openExternal'

export function PreflightStep({ flow }: { flow: UseSetupFlowReturn }) {
  if (!flow.preflightResult) return null

  const blockingFails = flow.preflightResult.checks.filter(
    (c) => c.status === 'fail' && BLOCKING_CHECK_IDS.has(c.id),
  )

  return (
    <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>System Check</h1>
      <p style={{ color: '#f87171', marginBottom: '1rem' }}>
        {blockingFails.length === 1
          ? 'One issue needs your attention before setup can continue.'
          : `${blockingFails.length} issues need your attention before setup can continue.`}
      </p>

      <div
        role="list"
        aria-label="Preflight check results"
        style={{ marginBottom: '1.25rem' }}
        data-testid="wizard-preflight-results"
      >
        {flow.preflightResult.checks
          .filter((c) => c.status !== 'pass')
          .map((check) => (
            <div
              key={check.id}
              role="listitem"
              data-testid={`wizard-preflight-check-${check.id}`}
              style={{
                padding: '0.75rem',
                marginBottom: '0.5rem',
                background: check.status === 'fail' ? 'rgba(239,68,68,0.08)' : 'rgba(251,191,36,0.08)',
                border: `1px solid ${check.status === 'fail' ? 'rgba(239,68,68,0.3)' : 'rgba(251,191,36,0.25)'}`,
                borderRadius: '6px',
              }}
            >
              <p style={{ margin: '0 0 0.25rem', fontWeight: 600, fontSize: '0.875rem',
                color: check.status === 'fail' ? '#f87171' : '#fde68a' }}>
                {check.name}
              </p>
              <p style={{ margin: 0, fontSize: '0.825rem', color: '#a1a1aa' }}>{check.message}</p>
              {check.fix_action && !(check.fix_action.kind === 'navigate' && check.fix_action.href !== '/model-manager') && (
                <button
                  onClick={() => {
                    const { kind, href } = check.fix_action!
                    if (kind === 'open-url') {
                      void openExternal(href)
                    } else if (kind === 'wizard-step') {
                      flow.setStep(href as UseSetupFlowReturn['step'])
                    } else if (href === '/model-manager') {
                      flow.setStep('choose')
                    } else {
                      flow.navigate(href)
                    }
                  }}
                  data-testid={`wizard-preflight-fix-${check.id}`}
                  style={{
                    marginTop: '0.5rem',
                    padding: '0.25rem 0.65rem',
                    borderRadius: '4px',
                    border: '1px solid rgba(255,255,255,0.15)',
                    background: 'rgba(255,255,255,0.06)',
                    color: '#93c5fd',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  {check.fix_action.label} →
                </button>
              )}
            </div>
          ))}
      </div>

      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
        <ActionButton onClick={() => flow.setStep('loading')}>Retry system check</ActionButton>
        <ActionButton onClick={() => flow.setStep('choose')}>Continue anyway</ActionButton>
      </div>
    </div>
  )
}
