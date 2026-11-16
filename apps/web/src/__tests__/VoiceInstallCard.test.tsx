// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import axe from 'axe-core'
import { VoiceInstallCard } from '../components/VoiceInstallCard'
import { formatDownloadSize, jobPercent, voiceInstallCardVisible } from '../lib/voiceInstall'
import type { UseVoiceInstall } from '../hooks/useVoiceInstall'
import { ENGINE, KOKORO, WHISPER, readyPlan, voiceJob, voicePlan } from './voiceFixtures'

function voice(overrides: Partial<UseVoiceInstall> = {}): UseVoiceInstall {
  return {
    status: voicePlan(),
    job: null,
    installing: false,
    busy: false,
    error: null,
    install: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

describe('formatDownloadSize', () => {
  it('states sizes the way a store page does', () => {
    expect(formatDownloadSize(558_764_242)).toBe('559 MB')
    expect(formatDownloadSize(2_500_000_000)).toBe('2.5 GB')
    expect(formatDownloadSize(7_252_012)).toBe('7.3 MB')
    expect(formatDownloadSize(687)).toBe('1 KB')
  })
})

describe('jobPercent', () => {
  it('weights progress by bytes, counting only stages whose size is known', () => {
    // 24.8 MB done + 80.3 MB of 160.6 MB, out of the 185.4 MB known so far.
    expect(jobPercent(voiceJob())).toBe(57)
  })

  it('is 100 for a finished job and 0 for one that has not started', () => {
    const done = voiceJob({ status: 'complete' })
    done.stages.forEach((s) => { s.state = 'complete'; s.bytes_total = s.bytes_total ?? 0 })
    expect(jobPercent(done)).toBe(100)
    const idle = voiceJob({ status: 'pending' })
    idle.stages.forEach((s) => { s.state = 'pending'; s.bytes_total = null; s.bytes_downloaded = null })
    expect(jobPercent(idle)).toBe(0)
  })
})

describe('VoiceInstallCard', () => {
  it('offers one install with its size, source and licence stated up front', () => {
    const v = voice()
    render(<VoiceInstallCard voice={v} />)

    expect(screen.getByText('Add voice')).toBeInTheDocument()
    expect(screen.getByText(/One download of 559 MB/)).toBeInTheDocument()
    expect(screen.getByText(/works offline afterwards/)).toBeInTheDocument()

    const button = screen.getByRole('button', { name: /install voice/i })
    expect(button).toHaveTextContent('559 MB')

    // The disclosure names every file's source and licence, and where it goes.
    const card = screen.getByTestId('voice-install')
    expect(within(card).getByText('Speech engine')).toBeInTheDocument()
    expect(within(card).getByText(/sherpa-onnx · Apache-2.0 · Includes ONNX Runtime/)).toBeInTheDocument()
    expect(within(card).getByText('Listening model (Whisper base)')).toBeInTheDocument()
    expect(within(card).getByText(/OpenAI Whisper, converted for sherpa-onnx · MIT/)).toBeInTheDocument()
    expect(within(card).getByText('Voices (Kokoro v1.0)')).toBeInTheDocument()
    expect(within(card).getByText(/checked against a pinned SHA-256/)).toBeInTheDocument()
    expect(within(card).getByText(/models\\voice/)).toBeInTheDocument()

    fireEvent.click(button)
    expect(v.install).toHaveBeenCalledTimes(1)
  })

  it('does not list what is already installed', () => {
    const plan = voicePlan({ download_bytes: 373_349_093 })
    plan.components[0] = { ...plan.components[0], ready: true, installed: true, download_bytes: 0 }
    plan.assets = [{ ...ENGINE, installed: true }, { ...WHISPER, installed: true }, KOKORO]
    render(<VoiceInstallCard voice={voice({ status: plan })} />)

    expect(screen.getByText('Add the character\u2019s voice')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /install character voice/i })).toHaveTextContent('373 MB')
    expect(screen.queryByText('Speech engine')).not.toBeInTheDocument()
    expect(screen.getByText('Voices (Kokoro v1.0)')).toBeInTheDocument()
  })

  it('names voice input when that is the only thing missing', () => {
    const plan = voicePlan()
    plan.components[1] = { ...plan.components[1], ready: true }
    render(<VoiceInstallCard voice={voice({ status: plan })} />)
    expect(screen.getByRole('button', { name: /install voice input/i })).toBeInTheDocument()
  })

  it('shows progress per step and lets the player cancel', () => {
    const v = voice({ job: voiceJob(), installing: true })
    render(<VoiceInstallCard voice={v} />)

    expect(screen.getByText('Installing voice')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: /voice install progress/i })).toHaveAttribute('aria-valuenow', '57')
    const steps = within(screen.getByRole('list', { name: /voice install steps/i }))
    expect(steps.getByText('Getting the speech engine')).toBeInTheDocument()
    expect(steps.getByText('Done')).toBeInTheDocument()
    expect(steps.getByText('80 MB of 161 MB')).toBeInTheDocument()
    expect(steps.getAllByText('Waiting')).toHaveLength(2)
    // Installing must not look like a second chance to start an install.
    expect(screen.queryByRole('button', { name: /install voice/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(v.cancel).toHaveBeenCalledTimes(1)
  })

  it('says what a full bar is still waiting for', () => {
    const job = voiceJob()
    job.stages[1] = { ...job.stages[1], detail: 'unpacking', bytes_downloaded: 160_609_290 }
    render(<VoiceInstallCard voice={voice({ job, installing: true })} />)
    expect(screen.getByText(/verifying and unpacking/i)).toBeInTheDocument()
  })

  it('reports a failure in the engine\u2019s words and offers to try again', () => {
    const job = voiceJob({
      status: 'failed',
      error_code: 'NETWORK',
      error_message: 'Could not connect to the download server.',
    })
    const v = voice({ job })
    render(<VoiceInstallCard voice={v} />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('The install did not finish.')
    expect(alert).toHaveTextContent('Could not connect to the download server.')
    expect(alert).toHaveTextContent(/trying again continues from there/)

    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(v.install).toHaveBeenCalledTimes(1)
  })

  it('does not promise a resume after a checksum failure', () => {
    const job = voiceJob({ status: 'failed', error_code: 'CHECKSUM', error_message: 'A downloaded file did not match.' })
    render(<VoiceInstallCard voice={voice({ job })} />)
    expect(screen.getByRole('alert')).not.toHaveTextContent(/continues from there/)
  })

  it('confirms a cancel left nothing behind', () => {
    render(<VoiceInstallCard voice={voice({ job: voiceJob({ status: 'cancelled' }) })} />)
    expect(screen.getByText(/no partial download was kept/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /install voice/i })).toBeInTheDocument()
  })

  it('confirms the install once voice is ready', () => {
    const job = voiceJob({ status: 'complete' })
    render(<VoiceInstallCard voice={voice({ status: readyPlan(), job })} />)
    expect(screen.getByRole('status')).toHaveTextContent('Voice is installed')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders nothing when voice already works', () => {
    const v = voice({ status: readyPlan() })
    const { container } = render(<VoiceInstallCard voice={v} />)
    expect(container).toBeEmptyDOMElement()
    expect(voiceInstallCardVisible(v)).toBe(false)
  })

  it('renders nothing when the engine has no installer', () => {
    const v = voice({ status: null })
    const { container } = render(<VoiceInstallCard voice={v} />)
    expect(container).toBeEmptyDOMElement()
    expect(voiceInstallCardVisible(v)).toBe(false)
  })

  it('explains an unsupported computer instead of offering a download', () => {
    const plan = voicePlan({
      supported: false,
      unsupported_reason: 'Voice is not available for this kind of computer yet.',
      download_bytes: 0,
    })
    render(<VoiceInstallCard voice={voice({ status: plan })} />)
    expect(screen.getByText(/not available for this kind of computer yet/)).toBeInTheDocument()
    expect(screen.getByText(/typing always works/i)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('disables its button while a request is in flight', () => {
    render(<VoiceInstallCard voice={voice({ busy: true })} />)
    expect(screen.getByRole('button', { name: /install voice/i })).toBeDisabled()
  })

  it.each([
    ['idle', voice()],
    ['installing', voice({ job: voiceJob(), installing: true })],
    ['failed', voice({ job: voiceJob({ status: 'failed', error_message: 'No.', error_code: 'UNKNOWN' }) })],
  ])('has no axe violations while %s', async (_name, v) => {
    const { container } = render(<VoiceInstallCard voice={v} />)
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(results.violations.map((x) => `${x.id}: ${x.nodes[0]?.html ?? ''}`)).toEqual([])
  })
})
