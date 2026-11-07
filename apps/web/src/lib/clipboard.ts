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

// Every fallback is announced on the console. When the last resort also fails,
// the button can only say "Copy failed", and the one informative error, the
// shell's reason for refusing the IPC call (a permission missing from the
// capability set, a window label the grant does not cover, a shell built
// without the plugin), would otherwise be gone. The prefix is stable so the
// line can be found in a devtools session or any console capture; the text
// being copied is never logged, since a diagnostics report can carry details
// a player would not want in a log file.
const WARN_PREFIX = '[clipboard]'

function reportFallback(mechanism: string, err: unknown): void {
  const reason = err instanceof Error ? err.message : String(err)
  console.warn(`${WARN_PREFIX} ${mechanism} failed, trying the next mechanism: ${reason}`)
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
    } catch (err) {
      // Permission missing, or an older shell without the plugin — try the web
      // APIs rather than dead-ending, but leave the shell's reason behind: on
      // macOS and Linux neither web API will work, and this is the only trace.
      reportFallback('desktop shell clipboard', err)
    }
  }
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard != null) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (err) {
    // fall through to the legacy path
    reportFallback('navigator.clipboard', err)
  }
  let textarea: HTMLTextAreaElement | undefined
  try {
    // Inside the try with everything else: this function's contract is that it
    // resolves false rather than throwing — three of its callers do not catch —
    // and `document` is absent outside a DOM altogether.
    if (typeof document === 'undefined') return false
    textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    // In a `finally` because execCommand is deprecated and already absent in
    // some engines, where calling it throws — and the scratch textarea was
    // selected, so leaving it behind parks focus in an invisible element on
    // the very error surface the user is trying to report from.
    textarea?.remove()
  }
}
