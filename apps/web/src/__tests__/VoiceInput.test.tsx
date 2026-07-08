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

  it('calls onSubmit with the transcript when uploadAudio returns one', async () => {
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

    expect(onSubmit).toHaveBeenCalledWith('hello world')
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

  it('does not call onSubmit with transcript when disabled, but populates the text input', async () => {
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

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox')).toHaveValue('hello world')
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
