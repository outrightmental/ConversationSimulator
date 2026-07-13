// SPDX-License-Identifier: Apache-2.0
import { useRef } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useSetupFlow, SetupFlowView } from '../setup'
import { SETUP_KEYS } from '../privacyPrefs'

export default function FirstRunWizard() {
  // Capture at mount only — setting localStorage mid-wizard must not trigger an
  // early redirect before the intended post-install navigation fires.
  const alreadyComplete = useRef(
    (() => { try { return localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true' } catch { return false } })()
  ).current

  // Resume an interrupted install: the guard forwards the pending install id in
  // `resume_install` so relaunching mid-download lands on the progress step
  // instead of a fresh Welcome (issue #380 acceptance criterion).
  const [params] = useSearchParams()
  const resumeRaw = params.get('resume_install')
  const resumeInstallId = resumeRaw != null && /^\d+$/.test(resumeRaw) ? Number(resumeRaw) : null

  const flow = useSetupFlow(
    resumeInstallId != null ? 'installing' : 'welcome',
    resumeInstallId ?? undefined,
  )

  if (alreadyComplete) {
    return <Navigate to="/" replace />
  }

  return <SetupFlowView flow={flow} mode="wizard" />
}
