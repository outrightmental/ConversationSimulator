// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest'
import { openExternal, isDesktopShell, installExternalLinkHandler } from '../lib/openExternal'

const win = window as unknown as { __TAURI__?: unknown }

afterEach(() => {
  delete win.__TAURI__
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('openExternal', () => {
  it('routes through the Tauri shell plugin in the desktop shell', async () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    win.__TAURI__ = { core: { invoke } }
    await openExternal('https://docs.example.com/setup')
    expect(invoke).toHaveBeenCalledWith('plugin:shell|open', { path: 'https://docs.example.com/setup' })
  })

  it('falls back to window.open in a plain browser', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    await openExternal('https://docs.example.com/setup')
    expect(open).toHaveBeenCalledWith('https://docs.example.com/setup', '_blank', 'noopener,noreferrer')
  })

  it('isDesktopShell reflects the Tauri bridge presence', () => {
    expect(isDesktopShell()).toBe(false)
    win.__TAURI__ = { core: { invoke: vi.fn() } }
    expect(isDesktopShell()).toBe(true)
  })
})

describe('installExternalLinkHandler', () => {
  it('is a no-op with no listener outside the desktop shell', () => {
    const add = vi.spyOn(document, 'addEventListener')
    const cleanup = installExternalLinkHandler()
    expect(add).not.toHaveBeenCalled()
    cleanup() // safe to call
  })

  it('intercepts external anchor clicks and opens them via the shell', async () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    win.__TAURI__ = { core: { invoke } }
    const cleanup = installExternalLinkHandler()

    const a = document.createElement('a')
    a.href = 'https://example.com/docs'
    a.target = '_blank'
    document.body.appendChild(a)

    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    a.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
    await Promise.resolve()
    expect(invoke).toHaveBeenCalledWith('plugin:shell|open', { path: 'https://example.com/docs' })
    cleanup()
  })

  it('ignores in-app (non-http) anchor clicks', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    win.__TAURI__ = { core: { invoke } }
    const cleanup = installExternalLinkHandler()

    const a = document.createElement('a')
    a.setAttribute('href', '/settings')
    document.body.appendChild(a)

    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 })
    a.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(false)
    expect(invoke).not.toHaveBeenCalled()
    cleanup()
  })

  it('ignores modifier-key clicks so users can still open in new windows', () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    win.__TAURI__ = { core: { invoke } }
    const cleanup = installExternalLinkHandler()

    const a = document.createElement('a')
    a.href = 'https://example.com/docs'
    document.body.appendChild(a)

    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ctrlKey: true })
    a.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(false)
    expect(invoke).not.toHaveBeenCalled()
    cleanup()
  })
})
