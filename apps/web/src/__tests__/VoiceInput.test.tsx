// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../hooks/useMicCapture', () => ({
  useMicCapture: vi.fn(),
  MAX_RECORDING_SECONDS: 60,
}))

vi.mock('../api/client', () => ({
  apiClient: {
    uploadAudio: vi.fn().mockResolvedValue({ transcript: null, status: 'received' }),
  },
}))

import { useMicCapture } from '../hooks/useMicCapture'
import VoiceInput from '../components/VoiceInput'
import type { MicPermission } from '../hooks/useMicCapture'

function makeMicState(overrides: Partial<ReturnType<typeof useMicCapture>> = {}) {
  return {
    permission: 'granted' as MicPermission,
    isRecording: false,
    recordingSeconds: 0,
    error: null,
    requestPermission: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(useMicCapture).mockReturnValue(makeMicState())
})

describe('VoiceInput — global Space hotkey focus guard', () => {
  it('calls startRecording when Space is pressed and no interactive element is focused', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ startRecording }))

    render(<VoiceInput />)
    // Blur anything that may have received focus during render.
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).toHaveBeenCalledOnce()
  })

  it('does not call startRecording when Space is pressed while the text input is focused', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ startRecording }))

    render(<VoiceInput />)
    screen.getByRole('textbox').focus()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()
  })

  it('does not call startRecording on repeated Space keydown (e.repeat guard)', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ startRecording }))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space', repeat: true })

    expect(startRecording).not.toHaveBeenCalled()
  })

  it('calls stopRecording on Space keyup when no interactive element is focused', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ stopRecording }))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).toHaveBeenCalledOnce()
  })

  it('does not call stopRecording on Space keyup while text input is focused', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ stopRecording }))

    render(<VoiceInput />)
    screen.getByRole('textbox').focus()

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).not.toHaveBeenCalled()
  })
})

describe('VoiceInput — text submission', () => {
  it('calls onSubmit with trimmed text and clears the input', () => {
    const onSubmit = vi.fn()
    render(<VoiceInput onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '  hello  ' } })
    fireEvent.submit(input.closest('form')!)

    expect(onSubmit).toHaveBeenCalledWith('hello')
    expect(input).toHaveValue('')
  })

  it('does not call onSubmit when text is empty', () => {
    const onSubmit = vi.fn()
    render(<VoiceInput onSubmit={onSubmit} />)

    fireEvent.submit(screen.getByRole('textbox').closest('form')!)

    expect(onSubmit).not.toHaveBeenCalled()
  })
})

describe('VoiceInput — denied / unsupported notices', () => {
  it('shows denied notice and keeps text input available when mic is denied', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'denied' }))
    render(<VoiceInput />)

    expect(screen.getByText(/microphone access denied/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('shows unsupported notice when mic is not available in this browser', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'unsupported' }))
    render(<VoiceInput />)

    expect(screen.getByText(/not supported in this browser/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })
})
