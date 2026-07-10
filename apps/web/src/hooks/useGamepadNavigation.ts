// SPDX-License-Identifier: Apache-2.0
/**
 * Polls the Gamepad API on every animation frame and translates controller
 * input into DOM events so the browser's native focus management drives all
 * D-pad navigation without a bespoke focus tree.
 *
 * Mappings (standard gamepad layout, matches Steam Deck):
 *   D-pad up / left-stick up   → focus previous interactive element
 *   D-pad down / left-stick dn → focus next interactive element
 *   D-pad left                 → focus previous interactive element
 *   D-pad right                → focus next interactive element
 *   A button (0)               → click / Enter on the focused element
 *   B button (1)               → Escape (back / close dialogs)
 *   R1 / RB (5)                → "gamepad-ptt-start" / "gamepad-ptt-stop"
 *                                  CustomEvents for push-to-talk in voice mode
 *
 * Elements (and their descendants) marked with [data-gamepad-exclude] are
 * excluded from the focus ring.  The DebugDrawer carries this attribute so
 * dev tooling does not interrupt controller navigation.
 */
import { useEffect } from 'react'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), textarea:not([disabled]), ' +
  '[tabindex]:not([tabindex="-1"]), details > summary'

// Minimum time (ms) before the same D-pad direction repeats while held.
const NAV_REPEAT_MS = 200

// Standard gamepad button indices (matches Xbox layout and Steam Deck).
const BTN_A = 0
const BTN_B = 1
const BTN_R1 = 5
const BTN_DPAD_UP = 12
const BTN_DPAD_DOWN = 13
const BTN_DPAD_LEFT = 14
const BTN_DPAD_RIGHT = 15

// Left-stick vertical axis index and dead-zone threshold.
const AXIS_LEFT_Y = 1
const STICK_DEAD_ZONE = 0.5

// True when the element (and every ancestor) is rendered — i.e. not hidden via
// `display:none` / `visibility:hidden` / the `hidden` attribute.  A hidden
// element cannot actually receive focus, so `.focus()` silently no-ops and the
// focus ring gets stuck on it forever.  The concrete offenders are the hidden
// `<input type="file">` controls used for pack import on Settings, Library, and
// Workbench — without this filter D-pad navigation soft-locks on those screens.
function isNavigable(el: HTMLElement): boolean {
  let node: HTMLElement | null = el
  while (node) {
    if (node.hidden) return false
    const style = window.getComputedStyle(node)
    if (style.display === 'none' || style.visibility === 'hidden') return false
    node = node.parentElement
  }
  return true
}

function getFocusableElements(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.closest('[data-gamepad-exclude]') && isNavigable(el),
  )
}

function moveFocus(direction: 'prev' | 'next'): void {
  const els = getFocusableElements()
  if (els.length === 0) return
  const current = document.activeElement
  const idx = current instanceof HTMLElement ? els.indexOf(current) : -1
  const next =
    direction === 'next'
      ? els[(idx + 1) % els.length]
      : els[(idx - 1 + els.length) % els.length]
  next?.focus({ preventScroll: false })
}

function activateFocused(): void {
  const el = document.activeElement
  if (!el || el === document.body) return
  if (el instanceof HTMLElement) {
    el.click()
  }
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
  el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }))
}

function pressEscape(): void {
  const el = document.activeElement ?? document.body
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }))
  el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }))
}

export function useGamepadNavigation(): void {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('getGamepads' in navigator)) return

    let rafId = 0
    // Previous-frame button pressed states, keyed by gamepad index.
    const prevPressed: Record<number, boolean[]> = {}
    // Timestamp of last navigation action per logical direction (shared for
    // up/left and down/right to avoid double-fires when both axes trigger).
    let lastNavForward = 0
    let lastNavBackward = 0

    function tick(): void {
      const gamepads = Array.from(navigator.getGamepads())
      const now = performance.now()

      for (const gp of gamepads) {
        if (!gp) continue
        const gi = gp.index
        if (!prevPressed[gi]) prevPressed[gi] = []

        const buttons = gp.buttons

        // Helper: true when this button was not pressed last frame but is now.
        const newPress = (bIdx: number): boolean => {
          const pressed = buttons[bIdx]?.pressed ?? false
          const prev = prevPressed[gi]?.[bIdx] ?? false
          return pressed && !prev
        }

        // ── D-pad + left-stick navigation ─────────────────────────────────────
        const stickY = gp.axes[AXIS_LEFT_Y] ?? 0
        const goBack =
          (buttons[BTN_DPAD_UP]?.pressed ?? false) ||
          (buttons[BTN_DPAD_LEFT]?.pressed ?? false) ||
          stickY < -STICK_DEAD_ZONE
        const goForward =
          (buttons[BTN_DPAD_DOWN]?.pressed ?? false) ||
          (buttons[BTN_DPAD_RIGHT]?.pressed ?? false) ||
          stickY > STICK_DEAD_ZONE

        if (goBack && now - lastNavBackward >= NAV_REPEAT_MS) {
          moveFocus('prev')
          lastNavBackward = now
          lastNavForward = now
        } else if (goForward && now - lastNavForward >= NAV_REPEAT_MS) {
          moveFocus('next')
          lastNavForward = now
          lastNavBackward = now
        }

        // ── A → activate focused element ──────────────────────────────────────
        if (newPress(BTN_A)) {
          activateFocused()
        }

        // ── B → Escape ────────────────────────────────────────────────────────
        if (newPress(BTN_B)) {
          pressEscape()
        }

        // ── R1 → push-to-talk ─────────────────────────────────────────────────
        const r1Now = buttons[BTN_R1]?.pressed ?? false
        const r1Prev = prevPressed[gi]?.[BTN_R1] ?? false
        if (r1Now && !r1Prev) {
          document.dispatchEvent(new CustomEvent('gamepad-ptt-start'))
        } else if (!r1Now && r1Prev) {
          document.dispatchEvent(new CustomEvent('gamepad-ptt-stop'))
        }

        // Snapshot current frame for next frame's edge detection.
        prevPressed[gi] = buttons.map((b) => b.pressed)
      }

      rafId = requestAnimationFrame(tick)
    }

    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [])
}
