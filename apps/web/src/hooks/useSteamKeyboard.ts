// SPDX-License-Identifier: Apache-2.0
/**
 * Shows the Steam floating on-screen keyboard automatically when a text input
 * or textarea receives focus.  This is required for Steam Deck Verified tier:
 * Valve's checklist mandates that every text field opens the keyboard without
 * manual player action.
 *
 * Outside Tauri (browser dev mode) or when Steam is not running the hook is a
 * complete no-op — all Tauri command calls are skipped gracefully.
 */
import { useEffect } from 'react'

type TauriCore = { invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> }

function getTauriCore(): TauriCore | null {
  const tauri = (
    window as { __TAURI__?: { core?: TauriCore } }
  ).__TAURI__
  return tauri?.core ?? null
}

function steamInvoke(command: string): void {
  const core = getTauriCore()
  if (!core) return
  core.invoke(command).catch(() => {
    // Steam not running or command unavailable — safe to ignore.
  })
}

export function useSteamKeyboard(): void {
  useEffect(() => {
    function handleFocusin(e: FocusEvent): void {
      const target = e.target
      if (!(target instanceof HTMLElement)) return
      const tag = target.tagName.toLowerCase()
      if (tag === 'input' || tag === 'textarea') {
        steamInvoke('steam_show_floating_keyboard')
      }
    }

    function handleFocusout(e: FocusEvent): void {
      const target = e.target
      if (!(target instanceof HTMLElement)) return
      const tag = target.tagName.toLowerCase()
      if (tag === 'input' || tag === 'textarea') {
        steamInvoke('steam_hide_floating_keyboard')
      }
    }

    document.addEventListener('focusin', handleFocusin)
    document.addEventListener('focusout', handleFocusout)
    return () => {
      document.removeEventListener('focusin', handleFocusin)
      document.removeEventListener('focusout', handleFocusout)
    }
  }, [])
}
