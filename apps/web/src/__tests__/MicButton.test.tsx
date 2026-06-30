// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MicButton from '../components/MicButton'
import type { MicPermission } from '../hooks/useMicCapture'

function makeProps(overrides: Partial<Parameters<typeof MicButton>[0]> = {}) {
  return {
    permission: 'granted' as MicPermission,
    isRecording: false,
    recordingSeconds: 0,
    isSubmitting: false,
    onRequestPermission: vi.fn(),
    onRecordStart: vi.fn(),
    onRecordStop: vi.fn(),
    ...overrides,
  }
}

describe('MicButton — permission states', () => {
  it('renders null when permission is unsupported', () => {
    const { container } = render(<MicButton {...makeProps({ permission: 'unsupported' })} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders null when permission is denied', () => {
    const { container } = render(<MicButton {...makeProps({ permission: 'denied' })} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders enable button when permission is idle', () => {
    render(<MicButton {...makeProps({ permission: 'idle' })} />)
    expect(screen.getByRole('button', { name: /enable microphone/i })).toBeInTheDocument()
  })

  it('calls onRequestPermission when enable button is clicked', () => {
    const onRequestPermission = vi.fn()
    render(<MicButton {...makeProps({ permission: 'idle', onRequestPermission })} />)
    fireEvent.click(screen.getByRole('button', { name: /enable microphone/i }))
    expect(onRequestPermission).toHaveBeenCalledOnce()
  })

  it('renders disabled requesting button while requesting', () => {
    render(<MicButton {...makeProps({ permission: 'requesting' })} />)
    const btn = screen.getByRole('button', { name: /requesting/i })
    expect(btn).toBeDisabled()
  })

  it('renders disabled processing button while submitting', () => {
    render(<MicButton {...makeProps({ isSubmitting: true })} />)
    const btn = screen.getByRole('button', { name: /processing/i })
    expect(btn).toBeDisabled()
  })
})

describe('MicButton — PTT behavior (granted)', () => {
  it('renders hold-to-record button when idle', () => {
    render(<MicButton {...makeProps()} />)
    expect(screen.getByRole('button', { name: /hold to record/i })).toBeInTheDocument()
  })

  it('shows aria-pressed=false when not recording', () => {
    render(<MicButton {...makeProps({ isRecording: false })} />)
    const btn = screen.getByRole('button', { name: /hold to record/i })
    expect(btn).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows aria-pressed=true when recording', () => {
    render(<MicButton {...makeProps({ isRecording: true, recordingSeconds: 5 })} />)
    const btn = screen.getByRole('button', { name: /recording/i })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  it('displays elapsed time while recording', () => {
    render(<MicButton {...makeProps({ isRecording: true, recordingSeconds: 42 })} />)
    expect(screen.getByRole('button', { name: /recording/i })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Recording 0:42')
  })

  it('calls onRecordStart on pointer down', () => {
    const onRecordStart = vi.fn()
    render(<MicButton {...makeProps({ onRecordStart })} />)
    fireEvent.pointerDown(screen.getByRole('button'))
    expect(onRecordStart).toHaveBeenCalledOnce()
  })

  it('calls onRecordStop on pointer up', () => {
    const onRecordStop = vi.fn()
    render(<MicButton {...makeProps({ onRecordStop })} />)
    fireEvent.pointerUp(screen.getByRole('button'))
    expect(onRecordStop).toHaveBeenCalledOnce()
  })

  it('calls onRecordStop on pointer leave', () => {
    const onRecordStop = vi.fn()
    render(<MicButton {...makeProps({ onRecordStop })} />)
    fireEvent.pointerLeave(screen.getByRole('button'))
    expect(onRecordStop).toHaveBeenCalledOnce()
  })

  it('calls onRecordStart on Space keydown', () => {
    const onRecordStart = vi.fn()
    render(<MicButton {...makeProps({ onRecordStart })} />)
    fireEvent.keyDown(screen.getByRole('button'), { code: 'Space' })
    expect(onRecordStart).toHaveBeenCalledOnce()
  })

  it('calls onRecordStop on Space keyup', () => {
    const onRecordStop = vi.fn()
    render(<MicButton {...makeProps({ onRecordStop })} />)
    fireEvent.keyUp(screen.getByRole('button'), { code: 'Space' })
    expect(onRecordStop).toHaveBeenCalledOnce()
  })

  it('does not call onRecordStart on repeated Space keydown', () => {
    const onRecordStart = vi.fn()
    render(<MicButton {...makeProps({ onRecordStart })} />)
    fireEvent.keyDown(screen.getByRole('button'), { code: 'Space', repeat: true })
    expect(onRecordStart).not.toHaveBeenCalled()
  })
})
