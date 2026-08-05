// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useSteamOverlay.
 *
 * The Tauri `invoke` API is not available in jsdom, so these tests verify:
 *  - The hook attaches and cleans up its keydown listener.
 *  - Outside Tauri (window.__TAURI__ absent) Shift+Tab is left untouched.
 *  - Under Tauri the chord is forwarded to `steam_activate_overlay` ONLY when
 *    Steam is enabled, and only for the bare Shift+Tab chord.
 *  - When forwarded, the default reverse-tab focus behaviour is prevented; when
 *    not forwarded, it is preserved (an accessibility requirement).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamOverlay } from '../hooks/useSteamOverlay'

// A mock Tauri `invoke` that answers `get_steam_status` with the given enabled
// flag and every other command with `true` (the overlay activation result).
function mockTauri(isSteamEnabled: boolean): ReturnType<typeof vi.fn> {
  const invoke = vi.fn((cmd: string) =>
    cmd === 'get_steam_status'
      ? Promise.resolve({ is_steam_enabled: isSteamEnabled })
      : Promise.resolve(true),
  )
  ;(window as unknown as Record<string, unknown>)['__TAURI__'] = { core: { invoke } }
  return invoke
}

function shiftTabEvent(overrides: KeyboardEventInit = {}): KeyboardEvent {
  return new KeyboardEvent('keydown', {
    key: 'Tab',
    shiftKey: true,
    bubbles: true,
    cancelable: true,
    ...overrides,
  })
}

describe('useSteamOverlay', () => {
  beforeEach(() => {
    delete (window as unknown as Record<string, unknown>)['__TAURI__']
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (window as unknown as Record<string, unknown>)['__TAURI__']
  })

  it('mounts and unmounts without throwing', () => {
    const { unmount } = renderHook(() => useSteamOverlay())
    expect(() => unmount()).not.toThrow()
  })

  it('registers and removes the keydown listener', () => {
    const addSpy = vi.spyOn(document, 'addEventListener')
    const removeSpy = vi.spyOn(document, 'removeEventListener')

    const { unmount } = renderHook(() => useSteamOverlay())
    expect(addSpy.mock.calls.map(([name]) => name)).toContain('keydown')

    unmount()
    expect(removeSpy.mock.calls.map(([name]) => name)).toContain('keydown')
  })

  it('does not throw and does not prevent default when __TAURI__ is absent', async () => {
    const { unmount } = renderHook(() => useSteamOverlay())

    const ev = shiftTabEvent()
    await act(async () => {
      document.dispatchEvent(ev)
    })

    // Standard reverse-tab navigation is preserved outside Tauri.
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })

  it('forwards Shift+Tab to steam_activate_overlay and prevents default when Steam is enabled', async () => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    // Let the get_steam_status query resolve so the chord becomes active.
    await act(async () => {})

    const ev = shiftTabEvent()
    await act(async () => {
      document.dispatchEvent(ev)
    })

    expect(invoke).toHaveBeenCalledWith('steam_activate_overlay')
    expect(ev.defaultPrevented).toBe(true)
    unmount()
  })

  it('leaves Shift+Tab untouched when Steam is not enabled', async () => {
    const invoke = mockTauri(false)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = shiftTabEvent()
    await act(async () => {
      document.dispatchEvent(ev)
    })

    // The overlay command is never sent, and reverse-tab navigation still works.
    expect(invoke).not.toHaveBeenCalledWith('steam_activate_overlay')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })

  it('ignores plain Tab (no Shift) under Steam', async () => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = shiftTabEvent({ shiftKey: false })
    await act(async () => {
      document.dispatchEvent(ev)
    })

    expect(invoke).not.toHaveBeenCalledWith('steam_activate_overlay')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })

  it.each([
    ['Ctrl', { ctrlKey: true }],
    ['Alt', { altKey: true }],
    ['Meta', { metaKey: true }],
  ])('ignores Shift+Tab when %s is also held under Steam', async (_label, mods) => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = shiftTabEvent(mods)
    await act(async () => {
      document.dispatchEvent(ev)
    })

    // Compound chords that include Tab must pass through untouched.
    expect(invoke).not.toHaveBeenCalledWith('steam_activate_overlay')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })

  it('ignores unrelated keys under Steam', async () => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = new KeyboardEvent('keydown', {
      key: 'a',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    await act(async () => {
      document.dispatchEvent(ev)
    })

    expect(invoke).not.toHaveBeenCalledWith('steam_activate_overlay')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })
})
