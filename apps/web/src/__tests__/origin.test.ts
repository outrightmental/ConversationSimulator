// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { CORE_ORIGIN, apiBaseFor, ttsAudioUrl } from '../api/origin'

describe('apiBaseFor', () => {
  it('is relative behind the dev proxy and absolute in a packaged build', () => {
    expect(apiBaseFor(false)).toBe('/api')
    expect(apiBaseFor(true)).toBe(`${CORE_ORIGIN}/api`)
  })
})

describe('ttsAudioUrl', () => {
  it('takes the file name from a Windows or a POSIX cache path', () => {
    expect(ttsAudioUrl('C:\\Users\\p\\cache\\tts\\abc123.wav')).toBe('/api/tts/audio/abc123.wav')
    expect(ttsAudioUrl('/home/p/.cache/tts/abc123.wav')).toBe('/api/tts/audio/abc123.wav')
  })

  it('carries the core origin in a packaged build, where the web view serves no /api', () => {
    // Issue #533: a bare /api/tts/audio/... resolved against tauri://localhost
    // and the character stayed silent.
    expect(ttsAudioUrl('C:\\cache\\abc123.wav', apiBaseFor(true))).toBe(
      'http://127.0.0.1:7355/api/tts/audio/abc123.wav',
    )
  })

  it('has no URL for a path with no file name', () => {
    expect(ttsAudioUrl('')).toBeNull()
    expect(ttsAudioUrl('/cache/tts/')).toBeNull()
  })
})
