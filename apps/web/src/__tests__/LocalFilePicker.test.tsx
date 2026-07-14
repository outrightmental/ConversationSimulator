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

  it('invokes plugin:dialog|open with correct payload when Browse is clicked', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker
        id="test-path"
        value=""
        onChange={() => {}}
        filters={[{ name: 'GGUF Model', extensions: ['gguf'] }]}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith('plugin:dialog|open', {
        payload: {
          title: 'Select file',
          filters: [{ name: 'GGUF Model', extensions: ['gguf'] }],
          multiple: false,
          directory: false,
        },
      }),
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

  it('does not call onChange when the dialog throws (error / unavailable)', async () => {
    const onChange = vi.fn()
    const invoke = vi.fn().mockRejectedValue(new Error('dialog unavailable'))
    win.__TAURI__ = { core: { invoke } }
    render(
      <LocalFilePicker id="test-path" value="/existing/path.gguf" onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /browse for file/i }))
    await waitFor(() => expect(invoke).toHaveBeenCalled())
    expect(onChange).not.toHaveBeenCalled()
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
        expect.objectContaining({ payload: expect.objectContaining({ filters: [] }) }),
      ),
    )
  })
})
