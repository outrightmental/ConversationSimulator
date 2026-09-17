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
 *  - F12 is forwarded to `steam_trigger_screenshot` under the same gating, once
 *    per physical press, with a transient non-interactive flash on success.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamOverlay, SCREENSHOT_FLASH_MS } from '../hooks/useSteamOverlay'

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

  // ── F12 → Steam screenshot ─────────────────────────────────────────────────

  function f12Event(overrides: KeyboardEventInit = {}): KeyboardEvent {
    return new KeyboardEvent('keydown', {
      key: 'F12',
      bubbles: true,
      cancelable: true,
      ...overrides,
    })
  }

  it('forwards F12 to steam_trigger_screenshot, prevents default, and flashes on success', async () => {
    vi.useFakeTimers()
    try {
      const invoke = mockTauri(true)

      const { unmount } = renderHook(() => useSteamOverlay())
      await act(async () => {})

      const ev = f12Event()
      await act(async () => {
        document.dispatchEvent(ev)
      })

      expect(invoke).toHaveBeenCalledWith('steam_trigger_screenshot')
      expect(ev.defaultPrevented).toBe(true)

      // Capture feedback: a transient, non-interactive flash element.
      const flash = document.querySelector('[data-testid="steam-screenshot-flash"]')
      expect(flash).not.toBeNull()
      expect((flash as HTMLElement).style.pointerEvents).toBe('none')
      expect(flash?.getAttribute('aria-hidden')).toBe('true')

      await act(async () => {
        vi.advanceTimersByTime(SCREENSHOT_FLASH_MS + 1)
      })
      expect(document.querySelector('[data-testid="steam-screenshot-flash"]')).toBeNull()
      unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not flash when the screenshot command reports failure', async () => {
    const invoke = vi.fn((cmd: string) =>
      cmd === 'get_steam_status'
        ? Promise.resolve({ is_steam_enabled: true })
        : Promise.resolve(false),
    )
    ;(window as unknown as Record<string, unknown>)['__TAURI__'] = { core: { invoke } }

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    await act(async () => {
      document.dispatchEvent(f12Event())
    })

    expect(invoke).toHaveBeenCalledWith('steam_trigger_screenshot')
    expect(document.querySelector('[data-testid="steam-screenshot-flash"]')).toBeNull()
    unmount()
  })

  it('leaves F12 untouched when Steam is not enabled', async () => {
    const invoke = mockTauri(false)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = f12Event()
    await act(async () => {
      document.dispatchEvent(ev)
    })

    // Devtools / host F12 behaviour is preserved outside Steam.
    expect(invoke).not.toHaveBeenCalledWith('steam_trigger_screenshot')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })

  it('takes one screenshot per physical press (ignores key auto-repeat)', async () => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    await act(async () => {
      document.dispatchEvent(f12Event({ repeat: true }))
    })

    expect(invoke).not.toHaveBeenCalledWith('steam_trigger_screenshot')
    unmount()
  })

  it.each([
    ['Ctrl', { ctrlKey: true }],
    ['Alt', { altKey: true }],
    ['Meta', { metaKey: true }],
    ['Shift', { shiftKey: true }],
  ])('ignores F12 when %s is also held under Steam', async (_label, mods) => {
    const invoke = mockTauri(true)

    const { unmount } = renderHook(() => useSteamOverlay())
    await act(async () => {})

    const ev = f12Event(mods)
    await act(async () => {
      document.dispatchEvent(ev)
    })

    expect(invoke).not.toHaveBeenCalledWith('steam_trigger_screenshot')
    expect(ev.defaultPrevented).toBe(false)
    unmount()
  })
})
