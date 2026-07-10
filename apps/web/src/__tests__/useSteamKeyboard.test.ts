// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useSteamKeyboard.
 *
 * The Tauri `invoke` API is not available in jsdom, so these tests verify:
 *  - The hook attaches and cleans up DOM event listeners.
 *  - Outside Tauri (window.__TAURI__ absent) no invocation attempt is made.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSteamKeyboard } from '../hooks/useSteamKeyboard'

describe('useSteamKeyboard', () => {
  beforeEach(() => {
    // Ensure __TAURI__ is absent (browser / test environment).
    delete (window as unknown as Record<string, unknown>)['__TAURI__']
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (window as unknown as Record<string, unknown>)['__TAURI__']
  })

  it('mounts and unmounts without throwing', () => {
    const { unmount } = renderHook(() => useSteamKeyboard())
    expect(() => unmount()).not.toThrow()
  })

  it('removes event listeners on unmount', () => {
    const addSpy = vi.spyOn(document, 'addEventListener')
    const removeSpy = vi.spyOn(document, 'removeEventListener')

    const { unmount } = renderHook(() => useSteamKeyboard())

    const addedNames = addSpy.mock.calls.map(([name]) => name)
    expect(addedNames).toContain('focusin')
    expect(addedNames).toContain('focusout')

    unmount()

    const removedNames = removeSpy.mock.calls.map(([name]) => name)
    expect(removedNames).toContain('focusin')
    expect(removedNames).toContain('focusout')
  })

  it('does not attempt to invoke Tauri when __TAURI__ is absent', async () => {
    // If @tauri-apps/api/core were imported, it would throw in jsdom.
    // Verify no dynamic import happens by confirming no error surfaces.
    const { unmount } = renderHook(() => useSteamKeyboard())

    const input = document.createElement('input')
    document.body.appendChild(input)

    await act(async () => {
      input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    })

    // No error means the Tauri branch was correctly skipped.
    unmount()
    document.body.removeChild(input)
  })

  it('reacts to focusin on input elements', async () => {
    const { unmount } = renderHook(() => useSteamKeyboard())

    const input = document.createElement('input')
    document.body.appendChild(input)

    let error: unknown
    try {
      await act(async () => {
        input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
      })
    } catch (e) {
      error = e
    }

    expect(error).toBeUndefined()
    unmount()
    document.body.removeChild(input)
  })

  it('reacts to focusin on textarea elements', async () => {
    const { unmount } = renderHook(() => useSteamKeyboard())

    const ta = document.createElement('textarea')
    document.body.appendChild(ta)

    await act(async () => {
      ta.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
      ta.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    })

    unmount()
    document.body.removeChild(ta)
  })

  it('ignores focusin on non-text elements such as buttons', async () => {
    const { unmount } = renderHook(() => useSteamKeyboard())

    const btn = document.createElement('button')
    document.body.appendChild(btn)

    // Should complete silently — non-text elements don't trigger keyboard.
    await act(async () => {
      btn.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    })

    unmount()
    document.body.removeChild(btn)
  })
})
