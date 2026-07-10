// SPDX-License-Identifier: Apache-2.0
/**
 * Shows the Steam floating on-screen keyboard automatically when a text-entry
 * input or textarea receives focus.  This is required for Steam Deck Verified
 * tier: Valve's checklist mandates that every text field opens the keyboard
 * without manual player action.  Toggle/selector inputs (checkbox, radio,
 * range, file, …) are deliberately excluded — they are driven with the gamepad
 * directly and a text keyboard would only obscure them.
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

// `<input>` types that accept typed text and therefore warrant the on-screen
// keyboard.  Toggle/selector inputs (checkbox, radio, range, file, color,
// button…) are driven directly with the gamepad, so popping a text keyboard for
// them would be wrong — it would obscure the very control the player is
// adjusting.  The native date/time pickers likewise have their own
// gamepad-friendly UI and are excluded.
const TEXT_INPUT_TYPES = new Set([
  'text',
  'search',
  'email',
  'url',
  'tel',
  'password',
  'number',
])

// True for a textarea or a text-entry `<input>`.  `HTMLInputElement.type`
// normalises a missing/unknown type attribute to `'text'`, so a bare `<input>`
// is correctly treated as text.
function isTextEntry(el: HTMLElement): boolean {
  if (el instanceof HTMLTextAreaElement) return true
  if (el instanceof HTMLInputElement) return TEXT_INPUT_TYPES.has(el.type)
  return false
}

export function useSteamKeyboard(): void {
  useEffect(() => {
    function handleFocusin(e: FocusEvent): void {
      const target = e.target
      if (!(target instanceof HTMLElement)) return
      if (isTextEntry(target)) {
        steamInvoke('steam_show_floating_keyboard')
      }
    }

    function handleFocusout(e: FocusEvent): void {
      const target = e.target
      if (!(target instanceof HTMLElement)) return
      if (isTextEntry(target)) {
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
