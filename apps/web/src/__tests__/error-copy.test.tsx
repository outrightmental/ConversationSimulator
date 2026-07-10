// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { I18nProvider, useTranslation, LOCALE_KEY, type TranslateFn } from '../i18n'
import { getErrorMessage } from '../error-copy'

// API error codes that error-copy.ts maps to localised messages. Kept in sync with
// the ERROR_KEYS map in error-copy.ts — this list is the contract under test.
const KNOWN_CODES = [
  'SCHEMA_VALIDATION_ERROR',
  'PACK_NOT_FOUND',
  'SCENARIO_NOT_FOUND',
  'SESSION_NOT_FOUND',
  'MODEL_NOT_LOADED',
  'RUNTIME_UNAVAILABLE',
  'SAFETY_VIOLATION',
  'TURN_LIMIT_EXCEEDED',
  'TURN_TIMEOUT',
  'INTERNAL_ERROR',
  'UNAUTHORIZED',
]

// Capture a real `t` bound to the given locale by rendering inside I18nProvider.
// The locale is seeded via localStorage so the provider initialises to it on mount
// (avoids a setState-during-render to switch after the fact).
function captureT(locale: string): TranslateFn {
  localStorage.setItem(LOCALE_KEY, locale)
  let captured: TranslateFn | null = null
  function Capture() {
    captured = useTranslation().t
    return null
  }
  render(
    <I18nProvider>
      <Capture />
    </I18nProvider>,
  )
  localStorage.clear()
  if (!captured) throw new Error('failed to capture t')
  return captured
}

describe('getErrorMessage', () => {
  const t = captureT('en')

  it('returns a localised message for every known error code (en)', () => {
    const unknown = t('errors.unknown')
    for (const code of KNOWN_CODES) {
      const msg = getErrorMessage(t, code)
      // Resolved to a real catalog string: not the raw key path and not the
      // generic unknown-error fallback.
      expect(msg.startsWith('errors.')).toBe(false)
      expect(msg).not.toBe(unknown)
      expect(msg.length).toBeGreaterThan(0)
    }
  })

  it('resolves German error copy for a known code', () => {
    const deT = captureT('de')
    expect(getErrorMessage(deT, 'PACK_NOT_FOUND')).toBe(
      'Das angeforderte Paket wurde nicht gefunden.',
    )
  })

  it('returns the provided fallback for an unknown code', () => {
    expect(getErrorMessage(t, 'NOPE_UNKNOWN_CODE', 'custom fallback')).toBe('custom fallback')
  })

  it('returns the generic unknown-error message for an unknown code with no fallback', () => {
    expect(getErrorMessage(t, 'NOPE_UNKNOWN_CODE')).toBe(t('errors.unknown'))
  })

  it('handles null and undefined codes via the generic message', () => {
    expect(getErrorMessage(t, null)).toBe(t('errors.unknown'))
    expect(getErrorMessage(t, undefined)).toBe(t('errors.unknown'))
  })

  it('prefers the fallback over the generic message when the code is null', () => {
    expect(getErrorMessage(t, null, 'my fallback')).toBe('my fallback')
  })
})
