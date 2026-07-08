// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DebugDrawer, { type DebugTurnEntry } from '../components/DebugDrawer'

const makeEntry = (overrides?: Partial<DebugTurnEntry>): DebugTurnEntry => ({
  turnId: 1,
  role: 'npc',
  rawPayload: {
    content: 'Hello, I am the NPC.',
    emotion: 'neutral',
    state_delta: { trust: 5 },
    event_flags: [],
    ending_type: null,
  },
  appliedDelta: { trust: 5 },
  ...overrides,
})

describe('DebugDrawer', () => {
  describe('rendering', () => {
    it('renders the debug drawer summary label', () => {
      render(<DebugDrawer entries={[]} />)
      expect(screen.getByText('Developer debug')).toBeInTheDocument()
    })

    it('renders the DEV badge', () => {
      render(<DebugDrawer entries={[]} />)
      expect(screen.getByText('DEV')).toBeInTheDocument()
    })

    it('shows entry count for empty entries', () => {
      render(<DebugDrawer entries={[]} />)
      expect(screen.getByText('0 entries')).toBeInTheDocument()
    })

    it('shows singular "entry" for one entry', () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      expect(screen.getByText('1 entry')).toBeInTheDocument()
    })

    it('shows plural "entries" for multiple entries', () => {
      render(<DebugDrawer entries={[makeEntry({ turnId: 1 }), makeEntry({ turnId: 2 })]} />)
      expect(screen.getByText('2 entries')).toBeInTheDocument()
    })

    it('has a data-testid of debug-drawer', () => {
      render(<DebugDrawer entries={[]} />)
      expect(screen.getByTestId('debug-drawer')).toBeInTheDocument()
    })
  })

  describe('content when opened', () => {
    it('shows developer mode warning note', () => {
      const { container } = render(<DebugDrawer entries={[makeEntry()]} />)
      const details = container.querySelector('[data-testid="debug-drawer"]') as HTMLDetailsElement
      details.open = true
      expect(screen.getByTestId('debug-drawer-content')).toBeInTheDocument()
    })

    it('shows "No debug entries yet" when entries are empty', () => {
      const { container } = render(<DebugDrawer entries={[]} />)
      const details = container.querySelector('[data-testid="debug-drawer"]') as HTMLDetailsElement
      details.open = true
      // The content is always rendered (details/summary reveals it)
      expect(screen.getByText(/no debug entries yet/i)).toBeInTheDocument()
    })

    it('renders raw payload JSON for an entry', () => {
      const entry = makeEntry()
      render(<DebugDrawer entries={[entry]} />)
      // JSON content is inside the debug drawer content div
      expect(screen.getByTestId('debug-drawer-content')).toBeInTheDocument()
    })

    it('shows "Turn 1" label for the first entry', () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      expect(screen.getByText('Turn 1')).toBeInTheDocument()
    })

    it('shows applied state delta badge when delta is non-empty', () => {
      render(<DebugDrawer entries={[makeEntry({ appliedDelta: { trust: 10 } })]} />)
      expect(screen.getByText('Δ state')).toBeInTheDocument()
    })

    it('does not show state delta badge when delta is empty', () => {
      render(<DebugDrawer entries={[makeEntry({ appliedDelta: {} })]} />)
      expect(screen.queryByText('Δ state')).not.toBeInTheDocument()
    })

    it('shows npc_opening role label', () => {
      render(<DebugDrawer entries={[makeEntry({ role: 'npc_opening' })]} />)
      expect(screen.getByText('(npc_opening)')).toBeInTheDocument()
    })
  })

  describe('hidden NPC agenda fields', () => {
    it('shows "agenda" badge when payload contains an agenda field', () => {
      const entry = makeEntry({
        rawPayload: {
          content: 'Hello.',
          agenda: 'Get the player to reveal financial info.',
        },
      })
      render(<DebugDrawer entries={[entry]} />)
      expect(screen.getByLabelText('Contains hidden NPC agenda fields')).toBeInTheDocument()
    })

    it('shows the agenda field names in the hidden NPC note', () => {
      const entry = makeEntry({
        rawPayload: {
          content: 'Hello.',
          hidden_state: 'suspicious',
        },
      })
      render(<DebugDrawer entries={[entry]} />)
      expect(screen.getByLabelText('Hidden NPC agenda fields')).toHaveTextContent('hidden_state')
    })

    it('does not show agenda badge for normal payload fields', () => {
      const entry = makeEntry({
        rawPayload: { content: 'Hello.', emotion: 'neutral' },
      })
      render(<DebugDrawer entries={[entry]} />)
      expect(screen.queryByLabelText('Contains hidden NPC agenda fields')).not.toBeInTheDocument()
    })
  })

  describe('copy to clipboard', () => {
    let writeMock: ReturnType<typeof vi.fn>

    beforeEach(() => {
      writeMock = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeMock },
        configurable: true,
      })
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('renders a copy button', () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      expect(screen.getByRole('button', { name: /copy turn json/i })).toBeInTheDocument()
    })

    it('calls clipboard.writeText when copy button clicked', async () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      fireEvent.click(screen.getByRole('button', { name: /copy turn json/i }))
      await waitFor(() => expect(writeMock).toHaveBeenCalledOnce())
    })

    it('does not include audio fields in copied text', async () => {
      const entry = makeEntry({
        rawPayload: {
          content: 'Hello.',
          audio_data: 'base64encodedaudio==',
          raw_audio: 'moredata',
        },
      })
      render(<DebugDrawer entries={[entry]} />)
      fireEvent.click(screen.getByRole('button', { name: /copy turn json/i }))
      await waitFor(() => expect(writeMock).toHaveBeenCalledOnce())
      const copiedText: string = writeMock.mock.calls[0][0] as string
      expect(copiedText).not.toContain('audio_data')
      expect(copiedText).not.toContain('raw_audio')
      expect(copiedText).toContain('Hello.')
    })

    it('shows redaction warning label', () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      expect(screen.getByText(/raw audio and secrets redacted/i)).toBeInTheDocument()
    })

    it('shows "Copied!" feedback after clicking copy', async () => {
      render(<DebugDrawer entries={[makeEntry()]} />)
      const btn = screen.getByRole('button', { name: /copy turn json/i })
      fireEvent.click(btn)
      await waitFor(() => expect(screen.getByText('Copied!')).toBeInTheDocument())
    })

    it('handles clipboard failure gracefully', async () => {
      writeMock.mockRejectedValue(new Error('Permission denied'))
      render(<DebugDrawer entries={[makeEntry()]} />)
      fireEvent.click(screen.getByRole('button', { name: /copy turn json/i }))
      await waitFor(() => expect(screen.getByText('Copy failed')).toBeInTheDocument())
    })
  })

  describe('multiple entries', () => {
    it('renders a turn item for each entry', () => {
      const entries = [
        makeEntry({ turnId: 1, role: 'npc_opening' }),
        makeEntry({ turnId: 2, role: 'npc' }),
        makeEntry({ turnId: 3, role: 'npc' }),
      ]
      render(<DebugDrawer entries={entries} />)
      expect(screen.getByText('Turn 1')).toBeInTheDocument()
      expect(screen.getByText('Turn 2')).toBeInTheDocument()
      expect(screen.getByText('Turn 3')).toBeInTheDocument()
    })
  })
})
