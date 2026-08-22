// SPDX-License-Identifier: Apache-2.0

export const VOICE_KEYS = {
  inviteState: 'convsim.voice.inviteState',
} as const

export type VoiceInviteState = 'pending' | 'dismissed' | 'setup'

export function readVoiceInviteState(): VoiceInviteState {
  if (typeof localStorage === 'undefined') return 'pending'
  const v = localStorage.getItem(VOICE_KEYS.inviteState)
  if (v === 'dismissed' || v === 'setup') return v
  return 'pending'
}

export function writeVoiceInviteState(state: VoiceInviteState): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(VOICE_KEYS.inviteState, state)
}

export const PRIVACY_KEYS = {
  saveTranscripts: 'convsim.privacy.saveTranscripts',
  saveTtsCache: 'convsim.privacy.saveTtsCache',
  saveRawAudio: 'convsim.privacy.saveRawAudio',
  devMode: 'convsim.devMode',
} as const

export const SETUP_KEYS = {
  firstRunComplete: 'convsim.setup.complete',
  // Legacy keys ('convsim.tutorial.complete', 'convsim.tutorial.install_id',
  // 'convsim.active_runtime_hint') were written by the removed no-model
  // demo/tutorial path (issue #473). Stale values are harmless: nothing reads
  // them any more.
} as const

export function readPrivacyPref(key: string, defaultValue: boolean): boolean {
  if (typeof localStorage === 'undefined') return defaultValue
  const v = localStorage.getItem(key)
  return v === null ? defaultValue : v === 'true'
}

export function writePrivacyPref(key: string, value: boolean): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(key, String(value))
}

/** Returns true when the developer debug drawer should be shown.
 *  Enabled by the VITE_DEV_TOOLS=true build flag or the per-device
 *  localStorage setting toggled in Settings → Advanced. */
export function isDevModeEnabled(): boolean {
  return (
    import.meta.env.VITE_DEV_TOOLS === 'true' ||
    readPrivacyPref(PRIVACY_KEYS.devMode, false)
  )
}
