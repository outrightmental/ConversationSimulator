// SPDX-License-Identifier: Apache-2.0
//
// Writing text to the system clipboard.
//
// Three mechanisms, tried in order, because no single one works everywhere the
// app runs (issue #508):
//
//   1. The Tauri clipboard plugin. This is the ONLY path that works in the
//      packaged macOS and Linux builds. There the webview is served from the
//      custom `tauri://localhost` scheme, which WKWebView does not treat as a
//      secure context, so `navigator.clipboard` is not defined at all; and
//      WebKit only honours `document.execCommand('copy')` while the user
//      gesture that triggered it is still live, which the diagnostics report's
//      own log-excerpt fetch has already outlived by the time we copy. Writing
//      through the plugin goes straight to the OS clipboard over IPC, with
//      neither restriction. (Windows was unaffected: its webview is served
//      from `https://tauri.localhost`, a secure context.)
//   2. `navigator.clipboard.writeText` — plain browsers and dev mode.
//   3. A hidden <textarea> + `document.execCommand('copy')` for older webviews
//      that have neither.
//
// This matters most for the "Copy diagnostics" button, whose whole job is to
// be the escape hatch when something else has already gone wrong — so it must
// never be the thing that fails.

type TauriInvoke = (cmd: string, args?: unknown) => Promise<unknown>

function getTauriInvoke(): TauriInvoke | undefined {
  if (typeof window === 'undefined') return undefined
  return (window as { __TAURI__?: { core?: { invoke?: TauriInvoke } } }).__TAURI__?.core?.invoke
}

/**
 * Write text to the system clipboard, preferring the desktop shell's native
 * clipboard and falling back to the two web APIs. Resolves false only when
 * every mechanism available in this environment failed.
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  const invoke = getTauriInvoke()
  if (invoke) {
    try {
      // Command and argument shape of tauri-plugin-clipboard-manager v2
      // (`writeText`); `label` is Android-only and intentionally omitted.
      await invoke('plugin:clipboard-manager|write_text', { text })
      return true
    } catch {
      // Permission missing, or an older shell without the plugin — try the web
      // APIs rather than dead-ending.
    }
  }
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard != null) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}
