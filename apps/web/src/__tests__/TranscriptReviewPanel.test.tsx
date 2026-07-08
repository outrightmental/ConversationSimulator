// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TranscriptReviewPanel from '../components/TranscriptReviewPanel'

function renderPanel(overrides: Partial<Parameters<typeof TranscriptReviewPanel>[0]> = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  const onRetry = vi.fn()
  render(
    <TranscriptReviewPanel
      transcript="hello world"
      onConfirm={onConfirm}
      onCancel={onCancel}
      onRetry={onRetry}
      {...overrides}
    />,
  )
  return { onConfirm, onCancel, onRetry }
}

describe('TranscriptReviewPanel — rendering', () => {
  it('renders the review panel with aria region label', () => {
    renderPanel()
    expect(screen.getByRole('region', { name: /transcript review/i })).toBeInTheDocument()
  })

  it('shows the transcript text in the editable textarea', () => {
    renderPanel()
    expect(screen.getByRole('textbox', { name: /edit transcript/i })).toHaveValue('hello world')
  })

  it('renders Submit, Retry, and Cancel buttons', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: /submit transcript/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry recording/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel and discard transcript/i })).toBeInTheDocument()
  })

  it('does not show hints section when language and confidence are absent', () => {
    renderPanel()
    expect(screen.queryByTestId('transcript-hints')).not.toBeInTheDocument()
  })

  it('shows the language hint when language is provided', () => {
    renderPanel({ language: 'en' })
    expect(screen.getByTestId('transcript-hints')).toHaveTextContent('Language: en')
  })

  it('shows the confidence hint when confidence is provided', () => {
    renderPanel({ confidence: 0.87 })
    expect(screen.getByTestId('transcript-hints')).toHaveTextContent('Confidence: 87%')
  })

  it('shows both language and confidence when both are provided', () => {
    renderPanel({ language: 'fr', confidence: 0.93 })
    const hints = screen.getByTestId('transcript-hints')
    expect(hints).toHaveTextContent('Language: fr')
    expect(hints).toHaveTextContent('Confidence: 93%')
  })

  it('rounds confidence to the nearest percent', () => {
    renderPanel({ confidence: 0.956 })
    expect(screen.getByTestId('transcript-hints')).toHaveTextContent('Confidence: 96%')
  })
})

describe('TranscriptReviewPanel — submit action', () => {
  it('calls onConfirm with the original transcript when Submit is clicked', () => {
    const { onConfirm } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))
    expect(onConfirm).toHaveBeenCalledWith('hello world')
  })

  it('calls onConfirm with edited text when the transcript is modified', () => {
    const { onConfirm } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.change(textarea, { target: { value: 'hello there' } })
    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))
    expect(onConfirm).toHaveBeenCalledWith('hello there')
  })

  it('trims surrounding whitespace before calling onConfirm', () => {
    const { onConfirm } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.change(textarea, { target: { value: '  hello  ' } })
    fireEvent.click(screen.getByRole('button', { name: /submit transcript/i }))
    expect(onConfirm).toHaveBeenCalledWith('hello')
  })

  it('disables the Submit button when the textarea is empty', () => {
    renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.change(textarea, { target: { value: '' } })
    expect(screen.getByRole('button', { name: /submit transcript/i })).toBeDisabled()
  })

  it('disables the Submit button when the textarea contains only whitespace', () => {
    renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.change(textarea, { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: /submit transcript/i })).toBeDisabled()
  })

  it('calls onConfirm on Ctrl+Enter in the textarea', () => {
    const { onConfirm } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })
    expect(onConfirm).toHaveBeenCalledWith('hello world')
  })

  it('calls onConfirm on Meta+Enter (Cmd+Enter) in the textarea', () => {
    const { onConfirm } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })
    expect(onConfirm).toHaveBeenCalledWith('hello world')
  })

  it('does not call onConfirm on plain Enter (without Ctrl/Meta)', () => {
    const { onConfirm } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

describe('TranscriptReviewPanel — cancel action', () => {
  it('calls onCancel when the Cancel button is clicked', () => {
    const { onCancel } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /cancel and discard transcript/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onCancel on Escape key in the textarea', () => {
    const { onCancel } = renderPanel()
    const textarea = screen.getByRole('textbox', { name: /edit transcript/i })
    fireEvent.keyDown(textarea, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledOnce()
  })
})

describe('TranscriptReviewPanel — retry action', () => {
  it('calls onRetry when the Retry button is clicked', () => {
    const { onRetry } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /retry recording/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
