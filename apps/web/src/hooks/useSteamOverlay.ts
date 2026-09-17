// SPDX-License-Identifier: Apache-2.0
/**
 * Forwards the Steam overlay chord (Shift+Tab) and the Steam screenshot hotkey
 * (F12) to the Tauri shell so they work on a Tauri app the way they do on a
 * native Steam title.
 *
 * Why this is necessary: Steam opens its overlay (and takes screenshots) when
 * it sees the hotkey in the *game* process via an input hook. A Tauri app
 * renders its UI in a separate WebView2 process (`msedgewebview2.exe`), so the
 * keystroke is delivered there and Steam's hook never sees it — both hotkeys
 * are silent no-ops by default. This hook listens for them in the webview and
 * forwards them:
 *
 *  - Shift+Tab → `steam_activate_overlay` (see `SteamRuntime::activate_overlay`)
 *  - F12       → `steam_trigger_screenshot` (see `SteamRuntime::trigger_screenshot`)
 *
 * The keys are only repurposed when Steam is actually active in this process
 * (`get_steam_status().is_steam_enabled`). Everywhere else — the browser build
 * and any desktop build without the Steamworks SDK running — Shift+Tab keeps
 * its standard "focus previous element" behaviour and F12 keeps whatever the
 * host gives it (devtools in the browser), both untouched.
 *
 * Rendering: opening the overlay is only visible if Steam has something to
 * draw into. On Windows the Rust side hosts a decoy compositing surface for
 * exactly that (vendored `tauri-plugin-steam-overlay-surface`); see the
 * "Steam overlay (Windows WebView2 caveat)" section of docs/STEAM_INTEGRATION.md.
 * This hook is the portable half of the fix — without it the chord is dead
 * even where that surface exists.
 *
 * Screenshot feedback: with hooked screenshots Steam plays no shutter sound and
 * its "screenshot saved" toast only appears once it has processed the file
 * (a few seconds later), so Valve's guidance is that the game supplies its own
 * feedback. We flash the page briefly when the capture command reports success.
 *
 * Known limitation (Windows): after alt-tabbing away and back, this listener is
 * deaf until the user clicks the page once, because Windows reactivates the
 * native window without returning keyboard focus to the webview. Do NOT try to
 * fix this by calling `webview.set_focus()` from the Rust focus handlers — doing
 * so kills Shift+Tab entirely, even on a fresh launch (a known, verified trap).
 *
 * Outside Tauri (browser dev mode) the hook is a complete no-op.
 */
import { useEffect } from 'react'

type TauriCore = { invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> }

function getTauriCore(): TauriCore | null {
  const tauri = (window as { __TAURI__?: { core?: TauriCore } }).__TAURI__
  return tauri?.core ?? null
}

/** How long the screenshot feedback flash stays on screen, in ms. */
export const SCREENSHOT_FLASH_MS = 120

/**
 * Brief full-page white flash as capture feedback. Pure DOM (no React state)
 * so it cannot re-render the app mid-session; `pointer-events: none` so it can
 * never intercept a click; `aria-hidden` so screen readers ignore it.
 */
export function flashScreenshotFeedback(doc: Document = document): void {
  const flash = doc.createElement('div')
  flash.setAttribute('data-testid', 'steam-screenshot-flash')
  flash.setAttribute('aria-hidden', 'true')
  flash.style.cssText =
    'position:fixed;inset:0;background:#fff;opacity:0.85;pointer-events:none;z-index:2147483647;'
  doc.body.appendChild(flash)
  window.setTimeout(() => {
    flash.remove()
  }, SCREENSHOT_FLASH_MS)
}

export function useSteamOverlay(): void {
  useEffect(() => {
    // Whether the overlay hotkeys can actually be serviced in this process.
    // Populated once from `get_steam_status`; until it resolves (and whenever
    // it is false) the keys are left alone so we never swallow the standard
    // reverse-tab affordance (or F12) in browser or non-Steam builds.
    let steamAvailable = false

    const core = getTauriCore()
    if (core) {
      core
        .invoke<{ is_steam_enabled?: boolean }>('get_steam_status')
        .then((status) => {
          steamAvailable = Boolean(status?.is_steam_enabled)
        })
        .catch(() => {
          // Steam status unavailable — leave the keys untouched.
        })
    }

    function handleKeydown(e: KeyboardEvent): void {
      // Bail when Ctrl/Alt/Meta are held so compound chords that happen to
      // include Tab or F12 are never swallowed.
      if (e.ctrlKey || e.altKey || e.metaKey) return
      if (!steamAvailable) return
      const activeCore = getTauriCore()
      if (!activeCore) return

      if (e.key === 'Tab' && e.shiftKey) {
        // Match only the bare Shift+Tab chord Steam reserves for the overlay.
        // Repurpose it as the overlay toggle exactly like a native Steam title:
        // prevent the webview from also cycling focus backwards behind the
        // overlay.
        e.preventDefault()
        activeCore.invoke('steam_activate_overlay').catch(() => {
          // Steam not running or command unavailable — safe to ignore.
        })
        return
      }

      if (e.key === 'F12' && !e.shiftKey) {
        // Steam's default screenshot hotkey. Auto-repeat would spam the
        // library; take one shot per physical press.
        if (e.repeat) return
        e.preventDefault()
        activeCore
          .invoke<boolean>('steam_trigger_screenshot')
          .then((captured) => {
            if (captured) flashScreenshotFeedback()
          })
          .catch(() => {
            // Steam not running or command unavailable — safe to ignore.
          })
      }
    }

    document.addEventListener('keydown', handleKeydown)
    return () => {
      document.removeEventListener('keydown', handleKeydown)
    }
  }, [])
}
