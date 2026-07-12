// SPDX-License-Identifier: Apache-2.0
//
// Opening external URLs from the desktop app.
//
// Inside the Tauri (WebView2 / WKWebView) webview, `window.open()` and clicks
// on `<a target="_blank">` are silently swallowed — no browser tab opens, so
// buttons like the preflight "Setup guide" appear to do nothing. The shell
// plugin's `open` command (already used to open local folders, see
// Support.tsx / Settings.tsx) hands the URL to the OS default handler, which
// is the supported way to open links in the user's browser.
//
// In a plain browser (dev at http://127.0.0.1:7354) the Tauri bridge is
// absent, so we fall back to native behaviour.

type TauriInvoke = (cmd: string, args?: unknown) => Promise<unknown>

function getTauriInvoke(): TauriInvoke | undefined {
  return (window as { __TAURI__?: { core?: { invoke?: TauriInvoke } } }).__TAURI__?.core?.invoke
}

/** True when running inside the Tauri desktop shell. */
export function isDesktopShell(): boolean {
  return getTauriInvoke() !== undefined
}

/**
 * Open an external URL in the user's default browser. In the desktop shell this
 * routes through the shell plugin; in a browser it falls back to `window.open`.
 */
export async function openExternal(href: string): Promise<void> {
  const invoke = getTauriInvoke()
  if (invoke) {
    await invoke('plugin:shell|open', { path: href })
    return
  }
  window.open(href, '_blank', 'noopener,noreferrer')
}

/**
 * Install a global click handler that routes external-link clicks through the
 * shell opener when running in the desktop shell. This makes every
 * `<a target="_blank" href="https://…">` open in the user's browser without
 * having to touch each call site. No-op (and no listener) in a plain browser,
 * where anchors already work. Returns a cleanup function.
 */
export function installExternalLinkHandler(): () => void {
  if (!isDesktopShell()) return () => {}

  const onClick = (e: MouseEvent) => {
    // Leave modified / non-primary clicks and already-handled events alone.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return
    }
    const anchor = (e.target as Element | null)?.closest?.('a')
    if (!anchor) return
    const href = anchor.getAttribute('href') ?? ''
    // Only intercept absolute http(s) URLs — internal SPA navigation uses
    // react-router <Link> (no raw <a href>), and schemes like mailto: are
    // handled fine by the OS already.
    if (!/^https?:\/\//i.test(href)) return
    e.preventDefault()
    void openExternal(href)
  }

  document.addEventListener('click', onClick)
  return () => document.removeEventListener('click', onClick)
}
