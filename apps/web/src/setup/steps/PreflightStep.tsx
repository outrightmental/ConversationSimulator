// SPDX-License-Identifier: Apache-2.0
import type { PreflightFixAction } from '@convsim/shared'
import { RemediationCard } from '../RemediationCard'
import type { UseSetupFlowReturn } from '../useSetupFlow'
import { openExternal } from '../../lib/openExternal'

export function PreflightStep({ flow }: { flow: UseSetupFlowReturn }) {
  if (!flow.preflightResult) return null

  // Only surface checks that genuinely need a human decision.
  // Auto-fixable failures are handled silently by the setup pipeline.
  // Informational warnings are shown in Settings → System health only.
  const needsHumanFails = flow.preflightResult.checks.filter(
    (c) => c.status === 'fail' && c.severity === 'needs-human',
  )

  // Extract core version from the runtime-handshake check for the copy block.
  const coreVersionMsg = flow.preflightResult.checks.find(
    (c) => c.id === 'runtime-handshake',
  )?.message ?? undefined

  function handleAction(action: PreflightFixAction) {
    const { kind, href } = action
    if (kind === 'open-url') {
      void openExternal(href)
    } else if (kind === 'wizard-step') {
      flow.setStep(href as UseSetupFlowReturn['step'])
    } else if (href === '/model-manager') {
      flow.setStep('choose')
    } else {
      flow.navigate(href)
    }
  }

  function handleTextOnly() {
    flow.setStep('choose')
  }

  return (
    <div style={{ maxWidth: '640px', margin: '2rem auto', padding: '0 1rem' }}>
      <h1 ref={flow.stepHeadingRef} tabIndex={-1} style={{ outline: 'none' }}>
        Getting things ready
      </h1>
      <p style={{ color: '#a1a1aa', marginBottom: '1.25rem' }}>
        {needsHumanFails.length === 1
          ? 'One thing needs your attention before setup can continue.'
          : `${needsHumanFails.length} things need your attention before setup can continue.`}
      </p>

      <div
        role="list"
        aria-label="Setup issues"
        data-testid="wizard-preflight-results"
      >
        {needsHumanFails.map((check) => (
          <div key={check.id} role="listitem" data-testid={`wizard-preflight-check-${check.id}`}>
            <RemediationCard
              check={check}
              onAction={handleAction}
              onTextOnly={handleTextOnly}
              coreVersion={coreVersionMsg}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
