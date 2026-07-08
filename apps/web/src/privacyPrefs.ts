// SPDX-License-Identifier: Apache-2.0

export const PRIVACY_KEYS = {
  saveTranscripts: 'convsim.privacy.saveTranscripts',
  saveTtsCache: 'convsim.privacy.saveTtsCache',
  saveRawAudio: 'convsim.privacy.saveRawAudio',
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
