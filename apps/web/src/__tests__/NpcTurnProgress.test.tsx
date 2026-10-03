// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import NpcTurnProgress from '../components/NpcTurnProgress'

function renderProgress(elapsedMs: number, estimateMs: number | null, streaming = false) {
  return render(
    <NpcTurnProgress
      active
      elapsedMs={elapsedMs}
      estimateMs={estimateMs}
      streaming={streaming}
    />,
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

    it('does not call a turn long until it passes the estimate it quoted', () => {
      // A 43s median is quoted as "45s", so "longer than the usual 45s" under a
      // clock reading 44s is the panel contradicting itself. The rounded figure
      // is the only one the player can check, so it is the one that decides.
      renderProgress(44_000, 43_000)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('44s / ~45s')
      // One second left of the 45s it quoted, and still counting down rather
      // than declaring itself wrong.
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent(/about 1s to go/i)
      expect(screen.getByTestId('npc-turn-progress-detail')).not.toHaveTextContent(/longer than/i)

      // And once it really is past the quoted figure, it says so.
      renderProgress(46_000, 43_000)
      expect(screen.getAllByTestId('npc-turn-progress-detail')[1]).toHaveTextContent(
        /longer than the usual 45s/i,
      )
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
      // The visible copy of the phrase is hidden, so it is not read twice.
      expect(screen.getByTestId('npc-turn-progress-heading')).toHaveAttribute(
        'aria-hidden',
        'true',
      )
    })

    it('carries the estimate in the announced phrase, not only in the hidden clock', () => {
      // The clock and caption are both aria-hidden and the elapsed-time status
      // does not fire until 30 s, so this is the only thing telling a
      // screen-reader user how long the turn will take — which is the whole of
      // issue #488. It is safe to announce because the estimate does not change
      // during a turn.
      renderProgress(2_000, 40_000)
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent(
        'NPC is thinking… Usually about 40s on this machine.',
      )
    })

    it('says outright that there is no estimate rather than going quiet', () => {
      renderProgress(2_000, null)
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent(
        'NPC is thinking… No turn has been timed on this machine yet.',
      )
    })

    it('says nothing about a wait that is still ordinary', () => {
      renderProgress(20_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('')
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

    it('says the turn is running long rather than leaving it to arithmetic', () => {
      // The amber caption says so outright and is aria-hidden; "1m 00s of about
      // 30s" is the same news in a form the player has to work out.
      renderProgress(70_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting on the NPC — 1m 00s, longer than the usual 30s. The reply is not lost.',
      )
    })

    it('does not announce "30s, longer than the usual 30s"', () => {
      // A 29s median is quoted as "30s", so the very first announcement — which
      // fires at exactly 30s — read as its own contradiction when it was judged
      // against the raw median.
      renderProgress(30_000, 29_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting on the NPC — 30s of about 30s. The reply is not lost.',
      )
    })

    it('waits for the announced figure to pass the estimate, not the clock', () => {
      // Judged against the ticking clock this would flip at 45s and announce
      // "30s, longer than the usual 45s" — off the grid and self-contradictory.
      renderProgress(50_000, 45_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting on the NPC — 30s of about 45s. The reply is not lost.',
      )
    })

    it('stops announcing a wait once the words are arriving', () => {
      // The transcript is a polite live region already reading the reply out;
      // "still waiting" over the top of it contradicts what the player hears.
      renderProgress(45_000, 30_000, true)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('')
    })
  })

  describe('between turns', () => {
    it('draws nothing but keeps its live regions mounted', () => {
      // A live region created in the same breath as its text is not reliably
      // announced, so the region that carries the estimate has to exist before
      // the turn does — the line this panel replaced was announced by the
      // transcript's own always-present region.
      render(<NpcTurnProgress active={false} elapsedMs={0} estimateMs={30_000} />)
      expect(screen.queryByTestId('npc-turn-progress')).not.toBeInTheDocument()
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent('')
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('')
    })

    it('starts announcing the moment a turn goes out', () => {
      const { rerender } = render(
        <NpcTurnProgress active={false} elapsedMs={0} estimateMs={40_000} />,
      )
      const status = screen.getByTestId('npc-turn-progress-status')
      rerender(<NpcTurnProgress active elapsedMs={0} estimateMs={40_000} />)
      // Same node, new text: that is the mutation a screen reader reads out.
      expect(screen.getByTestId('npc-turn-progress-status')).toBe(status)
      expect(status).toHaveTextContent('NPC is thinking… Usually about 40s on this machine.')
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
