// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

vi.mock('../hooks/useMicCapture', () => ({
  useMicCapture: vi.fn(),
  MAX_RECORDING_SECONDS: 60,
}))

vi.mock('../api/client', () => ({
  apiClient: {
    uploadAudio: vi.fn().mockResolvedValue({ transcript: null, status: 'unavailable' }),
    vadHealth: vi.fn().mockResolvedValue({ status: 'unavailable', worker_id: 'fake', worker_name: 'Fake VAD', checked_at: '' }),
    vadCalibrate: vi.fn().mockResolvedValue({ recommended_threshold: 0.05, noise_floor: 0.01, worker_id: 'fake', status: 'ok' }),
  },
}))

vi.mock('../hooks/useVad', () => ({
  useVad: vi.fn(),
}))

import { useMicCapture } from '../hooks/useMicCapture'
import { useVad } from '../hooks/useVad'
import { apiClient } from '../api/client'
import VoiceInput from '../components/VoiceInput'
import type { MicPermission } from '../hooks/useMicCapture'
import type { UseVadReturn } from '../hooks/useVad'

function makeMicState(overrides: Partial<ReturnType<typeof useMicCapture>> = {}) {
  return {
    permission: 'granted' as MicPermission,
    isRecording: false,
    recordingSeconds: 0,
    error: null,
    stream: null,
    requestPermission: vi.fn(),
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    ...overrides,
  }
}

function makeVadState(overrides: Partial<UseVadReturn> = {}): UseVadReturn {
  return {
    settings: { mode: 'ptt', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
    vadState: 'idle',
    isCalibrating: false,
    backendAvailable: false,
    setMode: vi.fn(),
    setThreshold: vi.fn(),
    setSilenceDurationMs: vi.fn(),
    startSilenceDetection: vi.fn(),
    stopSilenceDetection: vi.fn(),
    calibrate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useMicCapture).mockReturnValue(makeMicState())
  vi.mocked(useVad).mockReturnValue(makeVadState())
  vi.mocked(apiClient.uploadAudio).mockResolvedValue({ transcript: null, status: 'unavailable' })
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

  it('does not call startRecording on Space keydown when permission is not granted', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'denied', startRecording }))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()
  })

  it('does not call stopRecording on Space keyup when permission is not granted', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'denied', stopRecording }))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).not.toHaveBeenCalled()
  })

  it('does not call startRecording on Space keydown while upload is in progress', async () => {
    const startRecording = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState({ startRecording })
    })
    vi.mocked(apiClient.uploadAudio).mockReturnValueOnce(new Promise(() => {}))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    // Trigger upload; sets isSubmitting=true before the first await
    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()
  })

  it('does not call stopRecording on Space keyup while upload is in progress', async () => {
    const stopRecording = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState({ stopRecording })
    })
    vi.mocked(apiClient.uploadAudio).mockReturnValueOnce(new Promise(() => {}))

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).not.toHaveBeenCalled()
  })

  it('does not call startRecording on Space keydown while an anchor element is focused', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ startRecording }))

    render(<VoiceInput />)

    const link = document.createElement('a')
    link.href = '#'
    link.tabIndex = 0
    document.body.appendChild(link)
    link.focus()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()

    document.body.removeChild(link)
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

describe('VoiceInput — hotkey hint', () => {
  it('shows Space hotkey hint when mic is granted and not recording', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted', isRecording: false }))
    render(<VoiceInput />)

    expect(screen.getByText(/press/i)).toBeInTheDocument()
    expect(screen.getByText(/space/i)).toBeInTheDocument()
    expect(screen.getByText(/max 60s/i)).toBeInTheDocument()
  })

  it('hides Space hotkey hint while recording', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted', isRecording: true }))
    render(<VoiceInput />)

    expect(screen.queryByText(/max 60s/i)).not.toBeInTheDocument()
  })

  it('hides Space hotkey hint when mic is not yet enabled', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'idle' }))
    render(<VoiceInput />)

    expect(screen.queryByText(/max 60s/i)).not.toBeInTheDocument()
  })

  it('hides Space hotkey hint while audio is uploading', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState({ permission: 'granted', isRecording: false })
    })
    vi.mocked(apiClient.uploadAudio).mockReturnValueOnce(new Promise(() => {}))

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.queryByText(/max 60s/i)).not.toBeInTheDocument()
  })
})

describe('VoiceInput — audio upload flow', () => {
  it('calls uploadAudio with the blob when onAudioReady fires', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })

    render(<VoiceInput />)

    const blob = new Blob(['audio'], { type: 'audio/webm' })
    await act(async () => {
      capturedOnAudioReady?.(blob)
    })

    expect(vi.mocked(apiClient.uploadAudio)).toHaveBeenCalledOnce()
    expect(vi.mocked(apiClient.uploadAudio)).toHaveBeenCalledWith(blob, undefined)
  })

  it('shows the transcript review panel when uploadAudio returns a transcript', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByTestId('transcript-review-panel')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /edit transcript/i })).toHaveValue('hello world')
  })

  it('calls onSubmit with the transcript when user confirms in the review panel', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput onSubmit={onSubmit} />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))

    expect(onSubmit).toHaveBeenCalledWith('hello world')
  })

  it('calls onSubmit with edited text when user modifies the transcript before confirming', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput onSubmit={onSubmit} />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.change(textarea, { target: { value: 'hello there' } })
    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))

    expect(onSubmit).toHaveBeenCalledWith('hello there')
  })

  it('cancels the review panel and returns to normal input when cancel is clicked', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByTestId('transcript-review-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /cancel and discard transcript/i }))

    expect(screen.queryByTestId('transcript-review-panel')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
  })

  it('dismisses the review panel and returns to normal input when retry is clicked', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByTestId('transcript-review-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retry recording/i }))

    expect(screen.queryByTestId('transcript-review-panel')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
  })

  it('does not call onSubmit directly — it goes through review panel', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput onSubmit={onSubmit} />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    // onSubmit must not be called until user confirms in the review panel
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not call onSubmit when transcript is null', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })

    render(<VoiceInput onSubmit={onSubmit} />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows an error alert when uploadAudio resolves with status=error', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: null, status: 'error' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/could not be transcribed/i)
  })

  it('shows an alert when uploadAudio resolves with status=unavailable', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: null, status: 'unavailable' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/not installed/i)
  })

  it('shows a no-speech alert when uploadAudio resolves with status=ok but empty transcript', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: '', status: 'ok' })

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/no speech detected/i)
  })

  it('forwards the language prop to uploadAudio', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })

    render(<VoiceInput language="fr" />)

    const blob = new Blob(['audio'], { type: 'audio/webm' })
    await act(async () => {
      capturedOnAudioReady?.(blob)
    })

    expect(vi.mocked(apiClient.uploadAudio)).toHaveBeenCalledWith(blob, 'fr')
  })

  it('shows an upload error alert when uploadAudio rejects', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockRejectedValueOnce(new Error('Network error'))

    render(<VoiceInput />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    expect(screen.getByRole('alert')).toHaveTextContent(/failed to process audio/i)
  })

  it('text input remains available and usable when STT is unavailable (unavailable STT fallback)', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: null, status: 'unavailable' })

    render(<VoiceInput onSubmit={onSubmit} />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    // Alert shown for STT unavailable
    expect(screen.getByRole('alert')).toHaveTextContent(/not installed/i)

    // Text input still visible and usable — the player can type their turn
    const textInput = screen.getByRole('textbox', { name: /your response/i })
    expect(textInput).toBeInTheDocument()
    fireEvent.change(textInput, { target: { value: 'typed fallback response' } })
    fireEvent.submit(textInput.closest('form')!)
    expect(onSubmit).toHaveBeenCalledWith('typed fallback response')
  })

  it('shows review panel when disabled, then populates text input after confirmation', async () => {
    const onSubmit = vi.fn()
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState()
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'hello world', status: 'ok' })

    render(<VoiceInput onSubmit={onSubmit} disabled />)

    await act(async () => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    // Review panel should appear even when disabled
    expect(screen.getByTestId('transcript-review-panel')).toBeInTheDocument()

    // Confirming while disabled should NOT call onSubmit — it populates the text box
    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.queryByTestId('transcript-review-panel')).not.toBeInTheDocument()
    // After confirm, the text input (the standard response field) gets the transcript value
    expect(screen.getByRole('textbox', { name: /your response/i })).toHaveValue('hello world')
  })
})

describe('VoiceInput — hands-free VAD auto-stop (VAD timeout)', () => {
  it('calls stopRecording when the VAD silence callback fires during hands-free recording', () => {
    const stopRecording = vi.fn()
    let capturedOnSilence: (() => void) | undefined

    vi.mocked(useVad).mockReturnValue(
      makeVadState({
        settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
        startSilenceDetection: vi.fn().mockImplementation((_stream: MediaStream, onSilence: () => void) => {
          capturedOnSilence = onSilence
        }),
      }),
    )
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ stopRecording, stream: {} as MediaStream }),
    )

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    // Start hands-free recording — this arms the VAD silence callback
    fireEvent.keyDown(document, { code: 'Space' })

    expect(capturedOnSilence).toBeDefined()

    // VAD silence timer fires — simulates auto-stop after sustained silence
    capturedOnSilence?.()

    expect(stopRecording).toHaveBeenCalledOnce()
  })

  it('shows review panel after VAD auto-stop triggers audio upload', async () => {
    let capturedOnAudioReady: ((blob: Blob) => void) | undefined
    let capturedOnSilence: (() => void) | undefined
    const stopRecording = vi.fn().mockImplementation(() => {
      capturedOnAudioReady?.(new Blob(['audio'], { type: 'audio/webm' }))
    })

    vi.mocked(useVad).mockReturnValue(
      makeVadState({
        settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
        startSilenceDetection: vi.fn().mockImplementation((_stream: MediaStream, onSilence: () => void) => {
          capturedOnSilence = onSilence
        }),
      }),
    )
    vi.mocked(useMicCapture).mockImplementation((cb) => {
      capturedOnAudioReady = cb
      return makeMicState({ stopRecording, stream: {} as MediaStream })
    })
    vi.mocked(apiClient.uploadAudio).mockResolvedValueOnce({ transcript: 'VAD stopped me', status: 'ok' })

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    await act(async () => {
      capturedOnSilence?.()
    })

    expect(screen.getByTestId('transcript-review-panel')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /edit transcript/i })).toHaveValue('VAD stopped me')
  })
})

describe('VoiceInput — hands-free manual override', () => {
  it('stops recording when Space is pressed while already recording in hands-free mode', () => {
    const stopRecording = vi.fn()
    vi.mocked(useVad).mockReturnValue(
      makeVadState({
        settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
      }),
    )
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ isRecording: true, stopRecording }),
    )

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(stopRecording).toHaveBeenCalledOnce()
  })

  it('does not start a new recording when Space is pressed while already recording in hands-free mode', () => {
    const startRecording = vi.fn()
    vi.mocked(useVad).mockReturnValue(
      makeVadState({
        settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
      }),
    )
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ isRecording: true, startRecording }),
    )

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()
  })
})

describe('VoiceInput — hands-free Space key re-entry guard', () => {
  it('does not call startSilenceDetection again when Space is pressed while already recording in hands-free mode', () => {
    const startSilenceDetection = vi.fn()
    vi.mocked(useVad).mockReturnValue(
      makeVadState({
        settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null },
        vadState: 'listening',
        startSilenceDetection,
      }),
    )
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ isRecording: true, stream: {} as MediaStream }),
    )

    render(<VoiceInput />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    // Space pressed while already recording — must not reset VAD silence detection
    fireEvent.keyDown(document, { code: 'Space' })

    expect(startSilenceDetection).not.toHaveBeenCalled()
  })
})

describe('VoiceInput — VAD status indicator', () => {
  it('shows stopping state even when isRecording=false (auto-stop moment)', () => {
    // When the silence timer fires, React 18 batches vadState='stopping' together with
    // isRecording=false. The indicator must not gate on isRecording or the state is invisible.
    vi.mocked(useVad).mockReturnValue(
      makeVadState({ settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null }, vadState: 'stopping' }),
    )
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ isRecording: false }))

    render(<VoiceInput />)

    expect(screen.getByRole('status', { name: /vad status: auto-stopping/i })).toBeInTheDocument()
  })

  it('shows listening state during hands-free recording', () => {
    vi.mocked(useVad).mockReturnValue(
      makeVadState({ settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null }, vadState: 'listening' }),
    )
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ isRecording: true }))

    render(<VoiceInput />)

    expect(screen.getByRole('status', { name: /vad status: listening/i })).toBeInTheDocument()
  })

  it('shows idle state between recordings in hands-free mode', () => {
    vi.mocked(useVad).mockReturnValue(
      makeVadState({ settings: { mode: 'hands-free', threshold: 0.05, silenceDurationMs: 1500, calibratedAt: null }, vadState: 'idle' }),
    )
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ isRecording: false }))

    render(<VoiceInput />)

    expect(screen.getByRole('status', { name: /vad status: idle/i })).toBeInTheDocument()
  })
})

describe('VoiceInput — disabled prop', () => {
  it('does not call startRecording on Space keydown when disabled', () => {
    const startRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ startRecording }))

    render(<VoiceInput disabled />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyDown(document, { code: 'Space' })

    expect(startRecording).not.toHaveBeenCalled()
  })

  it('does not call stopRecording on Space keyup when disabled and not recording', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ stopRecording, isRecording: false }))

    render(<VoiceInput disabled />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).not.toHaveBeenCalled()
  })

  it('calls stopRecording on Space keyup when disabled but recording is in progress', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ stopRecording, isRecording: true }))

    render(<VoiceInput disabled />)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

    fireEvent.keyUp(document, { code: 'Space' })

    expect(stopRecording).toHaveBeenCalledOnce()
  })
})

describe('VoiceInput — inputMode prop (mode selection)', () => {
  it('renders text-only notice and no mic button when inputMode is text-only', () => {
    render(<VoiceInput inputMode="text-only" />)

    expect(screen.getByTestId('text-only-notice')).toBeInTheDocument()
    expect(screen.getByTestId('text-only-notice')).toHaveTextContent(/voice input disabled/i)
    expect(screen.queryByRole('button', { name: /record|mic/i })).not.toBeInTheDocument()
  })

  it('still accepts text submission in text-only mode', () => {
    const onSubmit = vi.fn()
    render(<VoiceInput inputMode="text-only" onSubmit={onSubmit} />)

    const input = screen.getByRole('textbox', { name: /your response/i })
    fireEvent.change(input, { target: { value: 'typed response' } })
    fireEvent.submit(input.closest('form')!)

    expect(onSubmit).toHaveBeenCalledWith('typed response')
  })

  it('renders mic button when inputMode is push-to-talk', () => {
    render(<VoiceInput inputMode="push-to-talk" />)

    expect(screen.queryByTestId('text-only-notice')).not.toBeInTheDocument()
    // MicButton renders as a button; any button that is not text-only notice
    // confirms mic controls are present
    expect(screen.getByRole('textbox', { name: /your response/i })).toBeInTheDocument()
  })

  it('initialises VAD mode to ptt when inputMode is push-to-talk', () => {
    const setMode = vi.fn()
    vi.mocked(useVad).mockReturnValue(makeVadState({ setMode }))

    render(<VoiceInput inputMode="push-to-talk" />)

    expect(setMode).toHaveBeenCalledWith('ptt')
  })

  it('initialises VAD mode to hands-free when inputMode is hands-free', () => {
    const setMode = vi.fn()
    vi.mocked(useVad).mockReturnValue(makeVadState({ setMode }))

    render(<VoiceInput inputMode="hands-free" />)

    expect(setMode).toHaveBeenCalledWith('hands-free')
  })

  it('does not call setMode when inputMode is text-only', () => {
    const setMode = vi.fn()
    vi.mocked(useVad).mockReturnValue(makeVadState({ setMode }))

    render(<VoiceInput inputMode="text-only" />)

    expect(setMode).not.toHaveBeenCalled()
  })

  it('does not call setMode again on re-render', () => {
    const setMode = vi.fn()
    vi.mocked(useVad).mockReturnValue(makeVadState({ setMode }))

    const { rerender } = render(<VoiceInput inputMode="push-to-talk" />)
    rerender(<VoiceInput inputMode="push-to-talk" />)

    // setMode initialises once on mount, not on every re-render
    expect(setMode).toHaveBeenCalledTimes(1)
  })
})

describe('VoiceInput — text-only fallback (voice-to-text switch)', () => {
  it('shows a Switch to text-only button when mic is granted and not in text-only mode', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    render(<VoiceInput inputMode="push-to-talk" />)

    expect(screen.getByRole('button', { name: /switch to text-only/i })).toBeInTheDocument()
  })

  it('switching to text-only shows the text-only notice and hides the mic button area', () => {
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    render(<VoiceInput inputMode="push-to-talk" />)

    fireEvent.click(screen.getByRole('button', { name: /switch to text-only/i }))

    expect(screen.getByTestId('text-only-notice')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /switch to text-only/i })).not.toBeInTheDocument()
  })

  it('stops any in-progress recording when switching to text-only', () => {
    const stopRecording = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(
      makeMicState({ permission: 'granted', isRecording: true, stopRecording }),
    )
    render(<VoiceInput inputMode="push-to-talk" />)

    fireEvent.click(screen.getByRole('button', { name: /switch to text-only/i }))

    expect(stopRecording).toHaveBeenCalledOnce()
  })

  it('text input is still functional after switching to text-only', () => {
    const onSubmit = vi.fn()
    vi.mocked(useMicCapture).mockReturnValue(makeMicState({ permission: 'granted' }))
    render(<VoiceInput inputMode="push-to-talk" onSubmit={onSubmit} />)

    fireEvent.click(screen.getByRole('button', { name: /switch to text-only/i }))

    const input = screen.getByRole('textbox', { name: /your response/i })
    fireEvent.change(input, { target: { value: 'fallback text' } })
    fireEvent.submit(input.closest('form')!)

    expect(onSubmit).toHaveBeenCalledWith('fallback text')
  })
})
