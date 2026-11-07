// SPDX-License-Identifier: Apache-2.0
//
// Clipboard write paths (issue #508). The packaged macOS build has neither web
// clipboard API available to it — `tauri://localhost` is not a secure context,
// so `navigator.clipboard` is undefined, and WebKit refuses
// `document.execCommand('copy')` once the user gesture is gone, which it is by
// the time the diagnostics report has been fetched. The desktop shell's own
// clipboard must therefore be tried first.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { copyTextToClipboard } from '../lib/clipboard'

const win = window as unknown as { __TAURI__?: unknown }

function stubTauri(invoke: (cmd: string, args?: unknown) => Promise<unknown>) {
  win.__TAURI__ = { core: { invoke } }
}

function stubNavigatorClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  return writeText
}

beforeEach(() => {
  delete win.__TAURI__
  delete (navigator as unknown as { clipboard?: unknown }).clipboard
  delete (document as unknown as { execCommand?: unknown }).execCommand
  // Each fallback is announced with console.warn. Capture it so the tests can
  // say what was reported, and so the expected failures stay out of the output.
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  delete win.__TAURI__
  delete (navigator as unknown as { clipboard?: unknown }).clipboard
  delete (document as unknown as { execCommand?: unknown }).execCommand
  vi.restoreAllMocks()
})

describe('copyTextToClipboard', () => {
  it('writes through the desktop shell when one is present', async () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    stubTauri(invoke)

    expect(await copyTextToClipboard('diagnostics report')).toBe(true)
    expect(invoke).toHaveBeenCalledWith('plugin:clipboard-manager|write_text', {
      text: 'diagnostics report',
    })
    expect(console.warn).not.toHaveBeenCalled()
  })

  it('succeeds in the desktop shell with no web clipboard API at all', async () => {
    // This is the packaged macOS case exactly: no navigator.clipboard, no
    // usable execCommand. Before the fix the button could only say "Copy failed".
    stubTauri(vi.fn().mockResolvedValue(undefined))
    expect(navigator.clipboard).toBeUndefined()

    expect(await copyTextToClipboard('report')).toBe(true)
  })

  it('prefers the shell over navigator.clipboard', async () => {
    const invoke = vi.fn().mockResolvedValue(undefined)
    stubTauri(invoke)
    const writeText = stubNavigatorClipboard()

    expect(await copyTextToClipboard('report')).toBe(true)
    expect(invoke).toHaveBeenCalled()
    expect(writeText).not.toHaveBeenCalled()
  })

  it('falls back to navigator.clipboard when the shell command fails', async () => {
    // e.g. a shell built without the clipboard permission in its capability set.
    stubTauri(vi.fn().mockRejectedValue(new Error('not allowed')))
    const writeText = stubNavigatorClipboard()

    expect(await copyTextToClipboard('report')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('report')
  })

  it('reports the shell rejection on the console, then still falls back', async () => {
    // The shell's reason is the only trace of a capability misconfiguration.
    // On macOS neither web API works, so without this line the button says
    // "Copy failed" and nothing anywhere says why.
    stubTauri(
      vi.fn().mockRejectedValue(new Error('Command plugin:clipboard-manager|write_text not allowed by ACL')),
    )
    const writeText = stubNavigatorClipboard()

    expect(await copyTextToClipboard('report with a player name in it')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('report with a player name in it')

    const warn = vi.mocked(console.warn)
    expect(warn).toHaveBeenCalledTimes(1)
    const line = String(warn.mock.calls[0][0])
    // A stable prefix so the line can be found in a devtools session or a
    // console capture, the shell's own message, and never the copied text.
    expect(line).toMatch(/^\[clipboard\] /)
    expect(line).toContain('not allowed by ACL')
    expect(line).not.toContain('player name')
  })

  it('reports a rejection the shell raised as a plain string', async () => {
    // An IPC call rejects with whatever the Rust side serialised, which for a
    // refused command is a string rather than an Error.
    stubTauri(vi.fn().mockRejectedValue('clipboard-manager.write_text not allowed'))
    stubNavigatorClipboard()

    expect(await copyTextToClipboard('report')).toBe(true)
    expect(String(vi.mocked(console.warn).mock.calls[0][0])).toContain(
      'clipboard-manager.write_text not allowed',
    )
  })

  it('still reports the shell rejection when every later mechanism fails too', async () => {
    // The packaged macOS case with a broken grant: no navigator.clipboard, no
    // execCommand. The result is false, and the reason is on the console.
    stubTauri(vi.fn().mockRejectedValue(new Error('not allowed')))

    expect(await copyTextToClipboard('report')).toBe(false)
    const warn = vi.mocked(console.warn)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0][0])).toContain('not allowed')
  })

  it('reports a navigator.clipboard rejection before trying execCommand', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('Write permission denied.')) },
      configurable: true,
    })
    ;(document as unknown as { execCommand: unknown }).execCommand = vi.fn().mockReturnValue(true)

    expect(await copyTextToClipboard('report')).toBe(true)
    const warn = vi.mocked(console.warn)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0][0])).toMatch(/^\[clipboard\] navigator\.clipboard .*Write permission denied\./)
  })

  it('uses navigator.clipboard in a plain browser', async () => {
    const writeText = stubNavigatorClipboard()
    expect(await copyTextToClipboard('report')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('report')
  })

  it('falls back to execCommand when navigator.clipboard rejects', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    })
    const execCommand = vi.fn().mockReturnValue(true)
    ;(document as unknown as { execCommand: unknown }).execCommand = execCommand

    expect(await copyTextToClipboard('report')).toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
    // The scratch textarea must not be left behind in the DOM.
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('reports failure when no mechanism works', async () => {
    expect(await copyTextToClipboard('report')).toBe(false)
  })

  it('leaves no scratch textarea behind when execCommand throws', async () => {
    // execCommand is deprecated and already gone from some engines, where
    // calling it throws rather than returning false. The scratch textarea was
    // selected by then, so leaving it in the DOM parks focus in an invisible
    // element on the very error surface the user is reporting from.
    ;(document as unknown as { execCommand: unknown }).execCommand = vi.fn(() => {
      throw new TypeError('document.execCommand is not a function')
    })

    expect(await copyTextToClipboard('report')).toBe(false)
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('resolves false rather than throwing when the DOM fallback cannot be built', async () => {
    // Callers in Settings, CreatorWorkbench and ScenarioLibrary do not catch,
    // so the last resort failing has to be a `false`, not a rejected promise.
    const createElement = vi
      .spyOn(document, 'createElement')
      .mockImplementation(() => {
        throw new TypeError('no DOM here')
      })
    try {
      await expect(copyTextToClipboard('report')).resolves.toBe(false)
    } finally {
      createElement.mockRestore()
    }
  })

  it('reports failure when execCommand declines the copy', async () => {
    ;(document as unknown as { execCommand: unknown }).execCommand = vi.fn().mockReturnValue(false)
    expect(await copyTextToClipboard('report')).toBe(false)
    expect(document.querySelector('textarea')).toBeNull()
  })
})
