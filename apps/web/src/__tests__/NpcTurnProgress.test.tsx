// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import NpcTurnProgress from '../components/NpcTurnProgress'

function renderProgress(elapsedMs: number, estimateMs: number | null, streaming = false) {
  return render(
    <NpcTurnProgress elapsedMs={elapsedMs} estimateMs={estimateMs} streaming={streaming} />,
  )
}

describe('NpcTurnProgress', () => {
  describe('with nothing measured yet', () => {
    it('still runs a clock, so the app never looks frozen', () => {
      renderProgress(7_000, null)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('7s')
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(
        /timing this turn so the next one can be estimated/i,
      )
    })

    it('reports no value rather than guessing one', () => {
      // 0% of an unknown total is a guess dressed as a fact.
      renderProgress(7_000, null)
      const bar = screen.getByRole('progressbar')
      expect(bar).not.toHaveAttribute('aria-valuenow')
      expect(bar).not.toHaveAttribute('aria-valuetext')
    })
  })

  describe('with an estimate from recent turns', () => {
    it('shows the wait against what this machine usually takes', () => {
      renderProgress(10_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('10s / ~30s')
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(
        /about 20s to go, based on recent turns \(usually 30s\)/i,
      )
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '33')
    })

    it('rounds the estimate it quotes, which a median does not deserve to the second', () => {
      renderProgress(5_000, 43_000)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('5s / ~45s')
    })

    it('never fills the bar while the reply is still out', () => {
      // A bar at 100% with nothing on screen reads as a turn the app lost.
      renderProgress(29_000, 30_000)
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '95')
    })

    it('admits the estimate was wrong instead of sitting at the end of the bar', () => {
      renderProgress(90_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(
        /longer than the usual 30s on this machine — the reply is not lost/i,
      )
      expect(screen.getByRole('progressbar')).toHaveAttribute(
        'aria-valuetext',
        '1m 30s elapsed, longer than the usual 30s',
      )
    })
  })

  describe('announcements', () => {
    it('keeps the ticking clock away from assistive tech', () => {
      // The clock changes every second; inside a live region that is ~300
      // announcements over a five-minute turn.
      renderProgress(45_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveAttribute('aria-hidden', 'true')
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveAttribute('aria-hidden', 'true')
    })

    it('announces the status phrase, which is the one thing that is not a clock', () => {
      // Nothing else on screen says the NPC is working once this panel is up.
      renderProgress(2_000, null)
      const status = screen.getByTestId('npc-turn-progress-status')
      expect(status).toHaveAttribute('role', 'status')
      expect(status).not.toHaveAttribute('aria-hidden')
      expect(status).toHaveTextContent('NPC is thinking…')
    })

    it('says nothing about a wait that is still ordinary', () => {
      renderProgress(20_000, 30_000)
      expect(screen.queryByTestId('npc-turn-progress-announcement')).not.toBeInTheDocument()
    })

    it('announces on a coarse grid once the wait is long', () => {
      const { unmount } = renderProgress(30_000, null)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting on the NPC — 30s so far. The reply is not lost.',
      )
      unmount()

      // Fifteen more seconds of ticking must not re-announce.
      renderProgress(45_000, null)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('45s')
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('30s so far')
    })

    it('crossing the next interval does announce', () => {
      renderProgress(61_000, null)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('1m 00s so far')
    })

    it('names the estimate when there is one', () => {
      renderProgress(45_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting on the NPC — 30s of about 30s. The reply is not lost.',
      )
    })

    it('stops announcing a wait once the words are arriving', () => {
      // The transcript is a polite live region already reading the reply out;
      // "still waiting" over the top of it contradicts what the player hears.
      renderProgress(45_000, 30_000, true)
      expect(screen.queryByTestId('npc-turn-progress-announcement')).not.toBeInTheDocument()
    })
  })

  describe('once the reply starts streaming', () => {
    it('stops claiming the NPC is thinking', () => {
      renderProgress(20_000, 30_000, true)
      const status = screen.getByTestId('npc-turn-progress-status')
      expect(status).toHaveTextContent('NPC is replying…')
      expect(status).not.toHaveTextContent('NPC is thinking…')
    })

    it('keeps timing the whole round trip, which is what was estimated', () => {
      renderProgress(20_000, 30_000, true)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('20s / ~30s')
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '67')
    })
  })
})
