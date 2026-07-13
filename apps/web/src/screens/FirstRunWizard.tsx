// SPDX-License-Identifier: Apache-2.0
import { useRef } from 'react'
import { Navigate } from 'react-router-dom'
import { useSetupFlow, SetupFlowView } from '../setup'
import { SETUP_KEYS } from '../privacyPrefs'

export default function FirstRunWizard() {
  // Capture at mount only — setting localStorage mid-wizard must not trigger an
  // early redirect before the intended post-install navigation fires.
  const alreadyComplete = useRef(
    (() => { try { return localStorage.getItem(SETUP_KEYS.firstRunComplete) === 'true' } catch { return false } })()
  ).current

  const flow = useSetupFlow('welcome')

  if (alreadyComplete) {
    return <Navigate to="/" replace />
  }

  return <SetupFlowView flow={flow} mode="wizard" />
}
