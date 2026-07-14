// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LocalFilePicker } from '../components/LocalFilePicker'

type TauriWindow = { __TAURI__?: unknown }
const win = window as unknown as TauriWindow

afterEach(() => {
  delete win.__TAURI__
})

// ── Basic rendering ─────────────────────────────────────────────────────────

describe('LocalFilePicker — basic rendering', () => {
  it('renders a text input with the given id', () => {
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    expect(document.getElementById('test-path')).toBeInTheDocument()
  })

  it('displays the current value', () => {
    render(
      <LocalFilePicker id="test-path" value="/some/file.gguf" onChange={() => {}} />,
    )
    expect(screen.getByRole('textbox')).toHaveValue('/some/file.gguf')
  })

  it('calls onChange when the text input changes', () => {
    const onChange = vi.fn()
    render(
      <LocalFilePicker id="test-path" value="" onChange={onChange} />,
    )
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '/new/path.gguf' } })
    expect(onChange).toHaveBeenCalledWith('/new/path.gguf')
  })

  it('applies the placeholder text', () => {
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} placeholder="/path/to/file.gguf" />,
    )
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', '/path/to/file.gguf')
  })

  it('marks the input aria-invalid when aria-invalid is true', () => {
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} aria-invalid={true} />,
    )
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('sets aria-describedby on the input', () => {
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} aria-describedby="hint-text" />,
    )
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-describedby', 'hint-text')
  })
})

// ── Non-Tauri environment ───────────────────────────────────────────────────

describe('LocalFilePicker — browser (non-Tauri) environment', () => {
  it('does not render a Browse button when window.__TAURI__ is absent', () => {
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    expect(screen.queryByRole('button', { name: /browse for file/i })).not.toBeInTheDocument()
  })
})

// ── Tauri environment ───────────────────────────────────────────────────────

describe('LocalFilePicker — Tauri desktop environment', () => {
  it('renders a Browse button when window.__TAURI__ is present', () => {
    win.__TAURI__ = { core: { invoke: vi.fn() } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    expect(screen.getByRole('button', { name: /browse for file/i })).toBeInTheDocument()
  })

  // The Tauri IPC layer keys command arguments by the Rust parameter name. The
  // `plugin:dialog|open` command takes `options: OpenDialogOptions`, so the args must
  // be nested under `options` — anything else fails to deserialize and the dialog
  // never opens. These tests mock `invoke`, so they are the only guard on that contract.
  it('invokes plugin:dialog|open with the args nested under `options`', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker
        id="test-path"
        value=""
        onChange={() => {}}
        filters={[{ name: 'GGUF Model', extensions: ['gguf'] }]}
        title="Select GGUF model file"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith('plugin:dialog|open', {
        options: {
          title: 'Select GGUF model file',
          filters: [{ name: 'GGUF Model', extensions: ['gguf'] }],
          defaultPath: undefined,
          multiple: false,
          directory: false,
        },
      }),
    )
  })

  it('opens the dialog at the path already in the field', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="/home/user/models/current.gguf" onChange={() => {}} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith(
        'plugin:dialog|open',
        expect.objectContaining({
          options: expect.objectContaining({ defaultPath: '/home/user/models/current.gguf' }),
        }),
      ),
    )
  })

  it('sends no defaultPath when the field is empty, rather than an empty string', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() => expect(invoke).toHaveBeenCalled())
    const options = (invoke.mock.calls[0][1] as { options: Record<string, unknown> }).options
    expect(options.defaultPath).toBeUndefined()
  })

  it('defaults the dialog title when no title prop is given', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith(
        'plugin:dialog|open',
        expect.objectContaining({ options: expect.objectContaining({ title: 'Select file' }) }),
      ),
    )
  })

  it('calls onChange with the selected path when the dialog returns a path', async () => {
    const onChange = vi.fn()
    const invoke = vi.fn().mockResolvedValue('/home/user/model.gguf')
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('/home/user/model.gguf'))
  })

  it('does not call onChange when the dialog is cancelled (returns null)', async () => {
    const onChange = vi.fn()
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="/existing/path.gguf" onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() => expect(invoke).toHaveBeenCalled())
    expect(onChange).not.toHaveBeenCalled()
  })

  it('tells the user and does not call onChange when the dialog throws (error / unavailable)', async () => {
    const onChange = vi.fn()
    const invoke = vi.fn().mockRejectedValue(new Error('dialog unavailable'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="/existing/path.gguf" onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    // A failed dialog must not leave a silently dead button: the user needs to know
    // the picker is unavailable and that typing the path still works.
    expect(await screen.findByRole('alert')).toHaveTextContent(/type the path directly/i)
    expect(errorSpy).toHaveBeenCalled()
    expect(onChange).not.toHaveBeenCalled()
    // The field keeps its value and the button is usable again for a retry.
    expect(screen.getByRole('textbox')).toHaveValue('/existing/path.gguf')
    expect(screen.getByRole('button', { name: /browse for file/i })).toBeEnabled()
    errorSpy.mockRestore()
  })

  it('does not open a second dialog while one is already open', async () => {
    let resolveDialog: (path: string | null) => void = () => {}
    const invoke = vi.fn().mockReturnValue(new Promise<string | null>((r) => { resolveDialog = r }))
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    const browse = screen.getByRole('button', { name: /browse for file/i })
    fireEvent.click(browse)
    await waitFor(() => expect(browse).toBeDisabled())
    fireEvent.click(browse)
    expect(invoke).toHaveBeenCalledTimes(1)

    resolveDialog(null)
    await waitFor(() => expect(browse).toBeEnabled())
  })

  it('passes an empty filters array when no filters prop is given', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={() => {}} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith(
        'plugin:dialog|open',
        expect.objectContaining({ options: expect.objectContaining({ filters: [] }) }),
      ),
    )
  })

  it('ignores a non-string dialog result instead of writing it into the path', async () => {
    const onChange = vi.fn()
    // `multiple: false` yields a string or null, but guard against an array leaking through.
    const invoke = vi.fn().mockResolvedValue(['/a.gguf', '/b.gguf'])
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="" onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() => expect(invoke).toHaveBeenCalled())
    expect(onChange).not.toHaveBeenCalled()
  })
})
