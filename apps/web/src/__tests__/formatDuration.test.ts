// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { formatDuration, formatApproxDuration } from '../lib/formatDuration'

describe('formatDuration', () => {
  it('reads as seconds under a minute', () => {
    expect(formatDuration(0)).toBe('0s')
    expect(formatDuration(8_400)).toBe('8s')
    expect(formatDuration(59_999)).toBe('59s')
  })

  it('pads the seconds once minutes are involved, so the clock does not jump width', () => {
    expect(formatDuration(60_000)).toBe('1m 00s')
    expect(formatDuration(125_000)).toBe('2m 05s')
    expect(formatDuration(600_000)).toBe('10m 00s')
  })

  it('floors a negative duration instead of printing a minus sign', () => {
    // A clock can read slightly negative if the device clock steps backwards
    // mid-turn; "-1s remaining" would look like a bug in the app.
    expect(formatDuration(-500)).toBe('0s')
  })
})

describe('formatApproxDuration', () => {
  it('rounds to the second below ten seconds', () => {
    expect(formatApproxDuration(4_200)).toBe('4s')
    expect(formatApproxDuration(9_600)).toBe('10s')
  })

  it('rounds to five seconds below a minute', () => {
    expect(formatApproxDuration(43_000)).toBe('45s')
    expect(formatApproxDuration(32_400)).toBe('30s')
  })

  it('rounds to ten seconds past a minute, where the last digit means nothing', () => {
    expect(formatApproxDuration(137_000)).toBe('2m 20s')
    expect(formatApproxDuration(184_000)).toBe('3m 00s')
  })

  it('never rounds down to nothing', () => {
    // "about 0s" is not an estimate — the smallest grain is the floor.
    expect(formatApproxDuration(0)).toBe('1s')
    expect(formatApproxDuration(120)).toBe('1s')
  })
})
