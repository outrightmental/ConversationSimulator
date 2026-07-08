// SPDX-License-Identifier: Apache-2.0

export const PRIVACY_KEYS = {
  saveTranscripts: 'convsim.privacy.saveTranscripts',
  saveTtsCache: 'convsim.privacy.saveTtsCache',
  saveRawAudio: 'convsim.privacy.saveRawAudio',
  devMode: 'convsim.devMode',
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
