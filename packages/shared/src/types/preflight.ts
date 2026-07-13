// SPDX-License-Identifier: Apache-2.0

export type CheckSeverity = 'auto-fixable' | 'needs-human' | 'informational'

export interface PreflightFixAction {
  kind: 'navigate' | 'open-url' | 'wizard-step' | 'install-engine'
  href: string
  label: string
}

export interface PreflightCheck {
  id: string
  name: string
  status: 'pass' | 'warn' | 'fail'
  message: string
  /** Triage class: determines whether this check blocks onboarding or is handled silently. */
  severity: CheckSeverity
  /** True if the setup pipeline can resolve this failure without user intervention. */
  autofix: boolean
  fix_action: PreflightFixAction | null
  /** Check-specific structured data (e.g. free_gb/required_gb for disk-space). */
  detail?: Record<string, unknown> | null
}

export interface PreflightResponse {
  overall: 'pass' | 'warn' | 'fail'
  checks: PreflightCheck[]
  ran_at: string
}
