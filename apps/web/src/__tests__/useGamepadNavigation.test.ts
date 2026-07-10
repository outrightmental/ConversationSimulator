// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useGamepadNavigation.
 *
 * The Gamepad API is not available in jsdom, so these tests replace
 * `navigator.getGamepads` with a controlled mock and drive the
 * requestAnimationFrame loop manually.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useGamepadNavigation } from '../hooks/useGamepadNavigation'

// ── Gamepad mock helpers ──────────────────────────────────────────────────────

type MockButton = { pressed: boolean; value: number; touched: boolean }

function makeButton(pressed: boolean): MockButton {
  return { pressed, value: pressed ? 1 : 0, touched: pressed }
}

function makeGamepad(overrides: Partial<{
  index: number
  buttons: MockButton[]
  axes: number[]
}>): Gamepad {
  const defaultButtons: MockButton[] = Array.from({ length: 17 }, () => makeButton(false))
  return {
    index: overrides.index ?? 0,
    id: 'Mock Gamepad',
    connected: true,
    mapping: 'standard' as GamepadMappingType,
    timestamp: performance.now(),
    buttons: overrides.buttons ?? defaultButtons,
    axes: overrides.axes ?? [0, 0, 0, 0],
  } as unknown as Gamepad
}

function makeButtons(pressedIndices: number[]): MockButton[] {
  return Array.from({ length: 17 }, (_, i) => makeButton(pressedIndices.includes(i)))
}

// ── RAF mock ──────────────────────────────────────────────────────────────────

// Replace rAF with a manual tick to control when the hook's polling loop runs.
let rafCallbacks: FrameRequestCallback[] = []
const rafMock = vi.fn((cb: FrameRequestCallback) => {
  rafCallbacks.push(cb)
  return rafCallbacks.length
})
const cancelRafMock = vi.fn((id: number) => {
  rafCallbacks = rafCallbacks.filter((_, i) => i + 1 !== id)
})

function flushRaf(): void {
  const cbs = [...rafCallbacks]
  rafCallbacks = []
  cbs.forEach((cb) => cb(performance.now()))
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useGamepadNavigation', () => {
  let getGamepadsMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    rafCallbacks = []
    vi.stubGlobal('requestAnimationFrame', rafMock)
    vi.stubGlobal('cancelAnimationFrame', cancelRafMock)

    getGamepadsMock = vi.fn().mockReturnValue([null])
    Object.defineProperty(navigator, 'getGamepads', {
      value: getGamepadsMock,
      configurable: true,
      writable: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    // Navigation sets this class on <html>; clear it so it can't leak between tests.
    document.documentElement.classList.remove('gamepad-active')
  })

  it('starts a requestAnimationFrame loop on mount', () => {
    renderHook(() => useGamepadNavigation())
    expect(rafMock).toHaveBeenCalledTimes(1)
  })

  it('cancels the rAF loop on unmount', () => {
    const { unmount } = renderHook(() => useGamepadNavigation())
    unmount()
    expect(cancelRafMock).toHaveBeenCalledTimes(1)
  })

  it('does not throw when no gamepads are connected', () => {
    getGamepadsMock.mockReturnValue([null, null])
    const { unmount } = renderHook(() => useGamepadNavigation())
    expect(() => flushRaf()).not.toThrow()
    unmount()
  })

  it('does not throw when getGamepads returns an empty list', () => {
    getGamepadsMock.mockReturnValue([])
    renderHook(() => useGamepadNavigation())
    expect(() => flushRaf()).not.toThrow()
  })

  it('dispatches gamepad-ptt-start when R1 is newly pressed', () => {
    const listener = vi.fn()
    document.addEventListener('gamepad-ptt-start', listener)

    const BTN_R1 = 5
    getGamepadsMock
      // First frame: R1 not pressed
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      // Second frame: R1 pressed
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_R1]) })])

    renderHook(() => useGamepadNavigation())

    flushRaf() // first frame — no press
    flushRaf() // second frame — rising edge on R1

    expect(listener).toHaveBeenCalledTimes(1)
    document.removeEventListener('gamepad-ptt-start', listener)
  })

  it('dispatches gamepad-ptt-stop when R1 is released', () => {
    const startListener = vi.fn()
    const stopListener = vi.fn()
    document.addEventListener('gamepad-ptt-start', startListener)
    document.addEventListener('gamepad-ptt-stop', stopListener)

    const BTN_R1 = 5
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])       // idle
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_R1]) })]) // press
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])        // release

    renderHook(() => useGamepadNavigation())

    flushRaf() // idle
    flushRaf() // press → gamepad-ptt-start
    flushRaf() // release → gamepad-ptt-stop

    expect(startListener).toHaveBeenCalledTimes(1)
    expect(stopListener).toHaveBeenCalledTimes(1)

    document.removeEventListener('gamepad-ptt-start', startListener)
    document.removeEventListener('gamepad-ptt-stop', stopListener)
  })

  it('does not dispatch gamepad-ptt-start on every frame while R1 is held', () => {
    const listener = vi.fn()
    document.addEventListener('gamepad-ptt-start', listener)

    const BTN_R1 = 5
    const pressedGp = makeGamepad({ buttons: makeButtons([BTN_R1]) })
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })]) // idle
      .mockReturnValue([pressedGp]) // held for subsequent frames

    renderHook(() => useGamepadNavigation())

    flushRaf() // idle
    flushRaf() // press — event fires once
    flushRaf() // still held — should NOT fire again
    flushRaf()

    expect(listener).toHaveBeenCalledTimes(1)
    document.removeEventListener('gamepad-ptt-start', listener)
  })

  it('moves focus to the next focusable element on D-pad down', () => {
    // Create two focusable buttons and attach them to the document.
    const btn1 = document.createElement('button')
    const btn2 = document.createElement('button')
    document.body.appendChild(btn1)
    document.body.appendChild(btn2)
    btn1.focus()
    expect(document.activeElement).toBe(btn1)

    const BTN_DPAD_DOWN = 13
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_DPAD_DOWN]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf() // idle
    flushRaf() // D-down press

    expect(document.activeElement).toBe(btn2)

    document.body.removeChild(btn1)
    document.body.removeChild(btn2)
  })

  it('marks <html> gamepad-active on navigation and clears it on real pointer input', () => {
    const btn1 = document.createElement('button')
    const btn2 = document.createElement('button')
    document.body.appendChild(btn1)
    document.body.appendChild(btn2)
    btn1.focus()

    const BTN_DPAD_DOWN = 13
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_DPAD_DOWN]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf() // idle
    flushRaf() // D-down press moves focus and flags gamepad mode

    // Without this class the CSS focus ring never shows for programmatic focus.
    expect(document.documentElement.classList.contains('gamepad-active')).toBe(true)

    // Pointer input returns to mouse mode and drops the ring.
    document.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(document.documentElement.classList.contains('gamepad-active')).toBe(false)

    document.body.removeChild(btn1)
    document.body.removeChild(btn2)
  })

  it('moves focus to the previous focusable element on D-pad up', () => {
    const btn1 = document.createElement('button')
    const btn2 = document.createElement('button')
    document.body.appendChild(btn1)
    document.body.appendChild(btn2)
    btn2.focus()
    expect(document.activeElement).toBe(btn2)

    const BTN_DPAD_UP = 12
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_DPAD_UP]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf()
    flushRaf()

    expect(document.activeElement).toBe(btn1)

    document.body.removeChild(btn1)
    document.body.removeChild(btn2)
  })

  it('skips elements inside [data-gamepad-exclude] during navigation', () => {
    const excluded = document.createElement('div')
    excluded.setAttribute('data-gamepad-exclude', '')
    const excludedBtn = document.createElement('button')
    excluded.appendChild(excludedBtn)

    const btn1 = document.createElement('button')
    const btn2 = document.createElement('button')
    document.body.appendChild(btn1)
    document.body.appendChild(excluded)
    document.body.appendChild(btn2)
    btn1.focus()

    const BTN_DPAD_DOWN = 13
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_DPAD_DOWN]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf()
    flushRaf()

    // btn2 is next because excludedBtn is skipped.
    expect(document.activeElement).toBe(btn2)

    document.body.removeChild(btn1)
    document.body.removeChild(excluded)
    document.body.removeChild(btn2)
  })

  it('skips hidden (display:none) inputs so navigation does not soft-lock', () => {
    // Regression: the hidden <input type="file"> used for pack import on
    // Settings/Library/Workbench cannot receive focus, so it must be excluded
    // from the focus ring — otherwise D-pad navigation gets stuck on it.
    const btn1 = document.createElement('button')
    const hidden = document.createElement('input')
    hidden.type = 'file'
    hidden.style.display = 'none'
    const btn2 = document.createElement('button')
    document.body.appendChild(btn1)
    document.body.appendChild(hidden)
    document.body.appendChild(btn2)
    btn1.focus()

    const BTN_DPAD_DOWN = 13
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_DPAD_DOWN]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf()
    flushRaf()

    // btn2 is next because the hidden file input is skipped.
    expect(document.activeElement).toBe(btn2)

    document.body.removeChild(btn1)
    document.body.removeChild(hidden)
    document.body.removeChild(btn2)
  })

  it('dispatches a click on the focused element when A is pressed', () => {
    const btn = document.createElement('button')
    const clickHandler = vi.fn()
    btn.addEventListener('click', clickHandler)
    document.body.appendChild(btn)
    btn.focus()

    const BTN_A = 0
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_A]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf()
    flushRaf()

    expect(clickHandler).toHaveBeenCalledTimes(1)
    document.body.removeChild(btn)
  })

  it('dispatches an Escape keydown when B is pressed (back / close)', () => {
    const seen: string[] = []
    const listener = (e: Event) => {
      seen.push((e as KeyboardEvent).key)
    }
    document.addEventListener('keydown', listener)

    const BTN_B = 1
    getGamepadsMock
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([]) })])
      .mockReturnValueOnce([makeGamepad({ buttons: makeButtons([BTN_B]) })])

    renderHook(() => useGamepadNavigation())
    flushRaf() // idle
    flushRaf() // B rising edge → Escape

    expect(seen).toContain('Escape')

    document.removeEventListener('keydown', listener)
  })
})
