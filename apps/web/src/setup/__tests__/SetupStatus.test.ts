// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { deriveSetupStatus } from '../SetupStatus'
import type { SetupStatusResponse } from '../SetupStatus'

describe('deriveSetupStatus', () => {
  it('returns never-run when kind is never-run', () => {
    const r: SetupStatusResponse = { kind: 'never-run' }
    expect(deriveSetupStatus(r)).toEqual({ kind: 'never-run' })
  })

  it('returns ready when kind is ready', () => {
    const r: SetupStatusResponse = { kind: 'ready' }
    expect(deriveSetupStatus(r)).toEqual({ kind: 'ready' })
  })

  it('returns incomplete with missing list when kind is incomplete', () => {
    const r: SetupStatusResponse = {
      kind: 'incomplete',
      missing: ['llm-present', 'packs-seeded'],
    }
    const result = deriveSetupStatus(r)
    expect(result.kind).toBe('incomplete')
    if (result.kind === 'incomplete') {
      expect(result.missing).toEqual(['llm-present', 'packs-seeded'])
    }
  })

  it('returns incomplete with empty missing list when none provided', () => {
    const r: SetupStatusResponse = { kind: 'incomplete' }
    const result = deriveSetupStatus(r)
    expect(result.kind).toBe('incomplete')
    if (result.kind === 'incomplete') {
      expect(result.missing).toEqual([])
    }
  })

  it('ready result ignores onboarding_outcome field', () => {
    const r: SetupStatusResponse = {
      kind: 'ready',
      onboarding_outcome: { outcome: 'completed-with-model', recorded_at: '2026-01-01T00:00:00Z' },
    }
    expect(deriveSetupStatus(r)).toEqual({ kind: 'ready' })
  })

  it('never-run result ignores onboarding_outcome field when null', () => {
    const r: SetupStatusResponse = { kind: 'never-run', onboarding_outcome: null }
    expect(deriveSetupStatus(r)).toEqual({ kind: 'never-run' })
  })

  it('incomplete result preserves all CheckId values', () => {
    const allCheckIds = [
      'llm-present',
      'packs-seeded',
      'llama-cpp-binary',
      'disk-space',
      'data-dir-writable',
      'voice-ready',
      'runtime-handshake',
    ] as const
    const r: SetupStatusResponse = { kind: 'incomplete', missing: [...allCheckIds] }
    const result = deriveSetupStatus(r)
    expect(result.kind).toBe('incomplete')
    if (result.kind === 'incomplete') {
      expect(result.missing).toHaveLength(allCheckIds.length)
    }
  })
})
