// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'

type TauriInvoke = <T>(cmd: string, args?: unknown) => Promise<T>
type TauriWindow = { __TAURI__?: { core?: { invoke?: TauriInvoke } } }

export interface DialogFilter {
  name: string
  extensions: string[]
}

interface LocalFilePickerProps {
  id: string
  value: string
  onChange: (value: string) => void
  /** File type filters shown in the native dialog (e.g. [{name:'GGUF',extensions:['gguf']}]). */
  filters?: DialogFilter[]
  /** Title of the native dialog window. */
  title?: string
  placeholder?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  disabled?: boolean
  inputStyle?: React.CSSProperties
}

function isTauriEnv(): boolean {
  return typeof (window as TauriWindow).__TAURI__ !== 'undefined'
}

/**
 * A path text input that adds a "Browse…" button in the Tauri desktop shell.
 * Clicking Browse opens the OS native file picker; the selected path fills the
 * input. The text field remains editable for direct typing in all environments.
 */
export function LocalFilePicker({
  id,
  value,
  onChange,
  filters,
  title,
  placeholder,
  disabled,
  inputStyle,
  ...ariaProps
}: LocalFilePickerProps) {
  const [inTauri] = useState(isTauriEnv)

  async function handleBrowse() {
    const tauri = (window as TauriWindow).__TAURI__
    const invoke = tauri?.core?.invoke
    if (!invoke) return
    try {
      // Tauri keys command arguments by the Rust parameter name; `plugin:dialog|open`
      // takes `options: OpenDialogOptions`, so the payload must be nested under `options`.
      const selected = await invoke<string | null>('plugin:dialog|open', {
        options: {
          title: title ?? 'Select file',
          filters: filters ?? [],
          multiple: false,
          directory: false,
        },
      })
      if (typeof selected === 'string') onChange(selected)
    } catch (err) {
      // Cancellation resolves to null rather than throwing, so a rejection here is a
      // real failure (shell unavailable, permission denied). Surface it instead of
      // failing silently, and leave the current value unchanged.
      console.error('Native file dialog failed', err)
    }
  }

  const inputBorder = ariaProps['aria-invalid']
    ? '1px solid rgba(239,68,68,0.6)'
    : '1px solid rgba(255,255,255,0.15)'

  return (
    <div style={{ display: 'flex', gap: '0.5rem', width: '100%' }}>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        aria-describedby={ariaProps['aria-describedby']}
        aria-invalid={ariaProps['aria-invalid']}
        style={{
          flex: 1,
          minWidth: 0,
          padding: '0.5rem 0.75rem',
          borderRadius: '4px',
          background: 'rgba(255,255,255,0.05)',
          border: inputBorder,
          color: 'inherit',
          fontFamily: 'monospace',
          fontSize: '0.875rem',
          boxSizing: 'border-box',
          ...inputStyle,
        }}
      />
      {inTauri && (
        <button
          type="button"
          onClick={() => void handleBrowse()}
          disabled={disabled}
          aria-label="Browse for file"
          style={{
            padding: '0.5rem 0.75rem',
            borderRadius: '4px',
            border: '1px solid rgba(255,255,255,0.2)',
            background: 'rgba(255,255,255,0.06)',
            color: 'inherit',
            cursor: disabled ? 'wait' : 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          Browse…
        </button>
      )}
    </div>
  )
}
