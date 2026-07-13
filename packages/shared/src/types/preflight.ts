// SPDX-License-Identifier: Apache-2.0

export interface PreflightFixAction {
  kind: 'navigate' | 'open-url' | 'wizard-step'
  href: string
  label: string
}

export interface PreflightCheck {
  id: string
  name: string
  status: 'pass' | 'warn' | 'fail'
  message: string
  fix_action: PreflightFixAction | null
}

export interface PreflightResponse {
  overall: 'pass' | 'warn' | 'fail'
  checks: PreflightCheck[]
  ran_at: string
}
