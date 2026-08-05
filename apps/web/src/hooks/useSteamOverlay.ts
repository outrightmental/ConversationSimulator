// SPDX-License-Identifier: Apache-2.0
/**
 * Forwards the Steam overlay chord (Shift+Tab) to the Tauri shell so the overlay
 * opens on a Tauri app the way it does on a native Steam title.
 *
 * Why this is necessary: Steam opens its overlay when it sees Shift+Tab in the
 * *game* process via an input hook. A Tauri app renders its UI in a separate
 * WebView2 process (`msedgewebview2.exe`), so the keystroke is delivered there
 * and Steam's hook never sees it — the default chord is a silent no-op. This
 * hook listens for Shift+Tab in the webview and forwards it to the
 * `steam_activate_overlay` command, which asks Steam to open the overlay
 * programmatically (see `SteamRuntime::activate_overlay`).
 *
 * The chord is only repurposed when Steam is actually active in this process
 * (`get_steam_status().is_steam_enabled`). Everywhere else — the browser build
 * and any desktop build without the Steamworks SDK running — Shift+Tab keeps its
 * standard "focus previous element" behaviour untouched.
 *
 * Windows caveat: opening the overlay is necessary but not sufficient for it to
 * be *visible* on Windows. Steam draws by hooking the game's graphics `Present`
 * call, and a Tauri app never presents a swapchain in its own process, so there
 * is nothing to composite the overlay into. Making it render requires a decoy
 * compositing surface on the Rust side; see the "Steam overlay (Windows WebView2
 * caveat)" section of docs/STEAM_INTEGRATION.md. This hook is the portable half
 * of the fix — without it the chord is dead even once that surface exists.
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

export function useSteamOverlay(): void {
  useEffect(() => {
    // Whether the overlay can actually be opened in this process. Populated once
    // from `get_steam_status`; until it resolves (and whenever it is false) the
    // chord is left alone so we never swallow the standard reverse-tab
    // affordance in browser or non-Steam builds.
    let overlayAvailable = false

    const core = getTauriCore()
    if (core) {
      core
        .invoke<{ is_steam_enabled?: boolean }>('get_steam_status')
        .then((status) => {
          overlayAvailable = Boolean(status?.is_steam_enabled)
        })
        .catch(() => {
          // Steam status unavailable — leave the chord untouched.
        })
    }

    function handleKeydown(e: KeyboardEvent): void {
      // Match only the bare Shift+Tab chord Steam reserves for the overlay.
      // Bail when Ctrl/Alt/Meta are also held so compound chords that happen to
      // include Tab are never swallowed.
      if (e.key !== 'Tab' || !e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) {
        return
      }
      if (!overlayAvailable) return
      const activeCore = getTauriCore()
      if (!activeCore) return
      // Repurpose the chord as the overlay toggle exactly like a native Steam
      // title: prevent the webview from also cycling focus backwards behind the
      // overlay.
      e.preventDefault()
      activeCore.invoke('steam_activate_overlay').catch(() => {
        // Steam not running or command unavailable — safe to ignore.
      })
    }

    document.addEventListener('keydown', handleKeydown)
    return () => {
      document.removeEventListener('keydown', handleKeydown)
    }
  }, [])
}
