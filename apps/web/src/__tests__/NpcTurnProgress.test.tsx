// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import axe from 'axe-core'
import NpcTurnProgress, { type NpcTurnProgressProps } from '../components/NpcTurnProgress'

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

    it('hatches the bar in a colour that can actually be seen', () => {
      // jsdom computes no contrast, so the token is what gets pinned. The hatch
      // used to alternate --cs-border with --cs-raise: two greys 1.2:1 apart,
      // which rendered as the empty bar the hatch exists not to be. --cs-text-faint
      // is 3.1:1 against the track, past the 3:1 floor for a non-text graphic.
      renderProgress(7_000, null)
      const fill = screen.getByTestId('npc-turn-progress-fill')
      expect(fill.getAttribute('style')).toContain('--cs-text-faint')
      expect(fill.getAttribute('style')).not.toContain('--cs-raise')
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

    it('does not fill the bar when the device clock steps backwards', () => {
      // formatDuration already floors a negative elapsed time at "0s"; the bar
      // has to floor too. "-2%" is not a CSS length, so the browser drops the
      // declaration and the fill falls back to the full width of its track —
      // the finished-looking bar the 95% ceiling exists to prevent.
      renderProgress(-500, 30_000)
      const bar = screen.getByRole('progressbar')
      expect(bar).toHaveAttribute('aria-valuenow', '0')
      expect(screen.getByTestId('npc-turn-progress-fill')).toHaveStyle({ width: '0%' })
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
      expect(status).toHaveTextContent('Thinking…')
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
        'Thinking… Usually about 40s on this machine.',
      )
    })

    it('says outright that there is no estimate rather than going quiet', () => {
      renderProgress(2_000, null)
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent(
        'Thinking… No turn has been timed on this machine yet.',
      )
    })

    it('says nothing about a wait that is still ordinary', () => {
      renderProgress(20_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('')
    })

    it('announces on a coarse grid once the wait is long', () => {
      const { unmount } = renderProgress(30_000, null)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting — 30s so far. The reply is not lost.',
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
        'Still waiting — 30s of about 30s. The reply is not lost.',
      )
    })

    it('says the turn is running long rather than leaving it to arithmetic', () => {
      // The amber caption says so outright and is aria-hidden; "1m 00s of about
      // 30s" is the same news in a form the player has to work out.
      renderProgress(70_000, 30_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting — 1m 00s, longer than the usual 30s. The reply is not lost.',
      )
    })

    it('does not announce "30s, longer than the usual 30s"', () => {
      // A 29s median is quoted as "30s", so the very first announcement — which
      // fires at exactly 30s — read as its own contradiction when it was judged
      // against the raw median.
      renderProgress(30_000, 29_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting — 30s of about 30s. The reply is not lost.',
      )
    })

    it('waits for the announced figure to pass the estimate, not the clock', () => {
      // Judged against the ticking clock this would flip at 45s and announce
      // "30s, longer than the usual 45s" — off the grid and self-contradictory.
      renderProgress(50_000, 45_000)
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent(
        'Still waiting — 30s of about 45s. The reply is not lost.',
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
      expect(screen.getByTestId('npc-turn-progress-hint')).toHaveTextContent('')
    })

    it('starts announcing the moment a turn goes out', () => {
      const { rerender } = render(
        <NpcTurnProgress active={false} elapsedMs={0} estimateMs={40_000} />,
      )
      const status = screen.getByTestId('npc-turn-progress-status')
      rerender(<NpcTurnProgress active elapsedMs={0} estimateMs={40_000} />)
      // Same node, new text: that is the mutation a screen reader reads out.
      expect(screen.getByTestId('npc-turn-progress-status')).toBe(status)
      expect(status).toHaveTextContent('Thinking… Usually about 40s on this machine.')
    })
  })

  describe('once the reply starts streaming', () => {
    it('stops claiming the NPC is thinking', () => {
      renderProgress(20_000, 30_000, true)
      const status = screen.getByTestId('npc-turn-progress-status')
      expect(status).toHaveTextContent('Replying…')
      expect(status).not.toHaveTextContent('Thinking…')
    })

    it('keeps timing the whole round trip, which is what was estimated', () => {
      renderProgress(20_000, 30_000, true)
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent('20s / ~30s')
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '67')
    })
  })

  describe('with stage events from the core (issue #539)', () => {
    function renderStage(props: Partial<NpcTurnProgressProps>) {
      return render(
        <NpcTurnProgress active elapsedMs={3_000} estimateMs={40_000} npcName="Dana" {...props} />,
      )
    }

    it('names the character and the stage, in the fiction', () => {
      renderStage({ stage: 'waiting' })
      expect(screen.getByTestId('npc-turn-progress-heading')).toHaveTextContent('Dana is getting ready…')
      expect(screen.getByTestId('npc-turn-progress')).toHaveAttribute('data-stage', 'waiting')
    })

    it('runs through the stages in order as the core reports them', () => {
      const { rerender } = renderStage({ stage: 'waiting' })
      const heading = () => screen.getByTestId('npc-turn-progress-heading').textContent
      expect(heading()).toBe('Dana is getting ready…')
      rerender(<NpcTurnProgress active elapsedMs={4_000} estimateMs={40_000} npcName="Dana" stage="reading" prompt={{ processed: 512, total: 2048, cached: 0 }} />)
      expect(heading()).toBe('Dana is thinking…')
      rerender(<NpcTurnProgress active elapsedMs={9_000} estimateMs={40_000} npcName="Dana" stage="writing" streaming />)
      expect(heading()).toBe('Dana is replying…')
      rerender(<NpcTurnProgress active elapsedMs={12_000} estimateMs={40_000} npcName="Dana" stage="checking" />)
      expect(heading()).toBe('Dana is trying that again…')
      rerender(<NpcTurnProgress active elapsedMs={13_000} estimateMs={40_000} npcName="Dana" stage="voice" />)
      expect(heading()).toBe('Getting the voice ready…')
    })

    it('falls back to the stage alone when the pack names no one', () => {
      render(<NpcTurnProgress active elapsedMs={3_000} estimateMs={null} stage="reading" />)
      expect(screen.getByTestId('npc-turn-progress-heading')).toHaveTextContent('Thinking…')
      expect(screen.getByTestId('npc-turn-progress-heading')).not.toHaveTextContent(/NPC/)
    })

    it('draws the reading bar as prompt read of total, with the cached share filled', () => {
      renderStage({ stage: 'reading', prompt: { processed: 1024, total: 2048, cached: 512 } })
      const bar = screen.getByRole('progressbar')
      expect(bar).toHaveAttribute('aria-valuenow', '50')
      expect(bar).toHaveAttribute('aria-valuetext', '50% of the conversation read')
      expect(screen.getByTestId('npc-turn-progress-fill')).toHaveStyle({ width: '50%' })
      expect(screen.getByTestId('npc-turn-progress-cached')).toHaveStyle({ width: '25%' })
      // The reading bar may reach the end: reading really does finish.
      renderStage({ stage: 'reading', prompt: { processed: 2048, total: 2048, cached: 0 } })
      expect(screen.getAllByRole('progressbar')[1]).toHaveAttribute('aria-valuenow', '100')
    })

    it('replaces the whole-turn clock and bar once stage events arrive', () => {
      renderStage({ stage: 'waiting' })
      // No "22s / ~40s", no "to go" caption, no time-based fill.
      expect(screen.getByTestId('npc-turn-progress-clock')).toHaveTextContent(/^3s$/)
      expect(screen.queryByTestId('npc-turn-progress-detail')).not.toBeInTheDocument()
      expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow')
    })

    it('quotes when the reply will start, as a range, and announces it once', () => {
      renderStage({ stage: 'reading', prompt: { processed: 256, total: 2048, cached: 0 }, replyStart: { lowMs: 5_000, highMs: 8_000 } })
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 5–8 s.')
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent(
        'Dana is thinking… Reply starts in about 5–8 s.',
      )
    })

    it('announces each stage once, not once per progress report', () => {
      // llama-server reports once per batch of prompt it reads, and every
      // report moves the estimate. The caption may follow it; the status
      // region is read out whole on every change, so it must not.
      const { rerender } = render(
        <NpcTurnProgress active elapsedMs={0} estimateMs={null} npcName="Dana" stage="waiting" replyStart={{ lowMs: 20_000, highMs: 35_000 }} />,
      )
      const status = screen.getByTestId('npc-turn-progress-status')
      const heard = new Set([status.textContent])
      const reports: Array<[number, number, number]> = [
        [200, 60_000, 120_000],
        [328, 55_000, 120_000],
        [456, 50_000, 60_000],
        [584, 45_000, 70_000],
        [712, 40_000, 55_000],
      ]
      for (const [processed, lowMs, highMs] of reports) {
        rerender(
          <NpcTurnProgress active elapsedMs={2_000} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed, total: 2200, cached: 0 }} replyStart={{ lowMs, highMs }} />,
        )
        heard.add(status.textContent)
      }
      // The caption is current …
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 40–55 s.')
      // … and the status changed once per stage, carrying the estimate the
      // stage began with.
      expect([...heard]).toEqual([
        'Dana is getting ready… Reply starts in about 20–35 s.',
        'Dana is thinking… Reply starts in about 1–2 min.',
      ])
    })

    it('carries the current estimate in the half-minute announcement, on the same grid', () => {
      const at = (elapsedMs: number, lowMs: number, highMs: number) => (
        <NpcTurnProgress active elapsedMs={elapsedMs} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed: 400, total: 2200, cached: 0 }} replyStart={{ lowMs, highMs }} />
      )
      const { rerender } = render(at(29_000, 60_000, 120_000))
      const announcement = screen.getByTestId('npc-turn-progress-announcement')
      expect(announcement).toHaveTextContent('')
      rerender(at(31_000, 40_000, 55_000))
      expect(announcement).toHaveTextContent('Still waiting on Dana — 30s so far. The reply is not lost. Reply starts in about 40–55 s.')
      // A report between grid points moves the caption, not the announcement.
      rerender(at(45_000, 30_000, 45_000))
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 30–45 s.')
      expect(announcement).toHaveTextContent('Still waiting on Dana — 30s so far. The reply is not lost. Reply starts in about 40–55 s.')
      rerender(at(61_000, 10_000, 15_000))
      expect(announcement).toHaveTextContent('Still waiting on Dana — 1m 00s so far. The reply is not lost. Reply starts in about 10–15 s.')
    })

    it('quotes a wait of a minute or more in minutes, the way the clock beside it reads', () => {
      const { unmount } = renderStage({ stage: 'reading', prompt: { processed: 200, total: 2200, cached: 0 }, replyStart: { lowMs: 60_000, highMs: 120_000 } })
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 1–2 min.')
      expect(screen.getByTestId('npc-turn-progress-detail')).not.toHaveTextContent(/\d{3}/)
      unmount()
      // A range that crosses the minute gives each end its own unit.
      renderStage({ stage: 'reading', prompt: { processed: 200, total: 2200, cached: 0 }, replyStart: { lowMs: 55_000, highMs: 120_000 } })
      expect(screen.getByTestId('npc-turn-progress-detail')).toHaveTextContent('Reply starts in about 55 s–2 min.')
    })

    it('shows no estimate when none was given: writing, or under the threshold', () => {
      renderStage({ stage: 'writing', streaming: true, replyStart: null })
      expect(screen.queryByTestId('npc-turn-progress-detail')).not.toBeInTheDocument()
      expect(screen.getByTestId('npc-turn-progress-announcement')).toHaveTextContent('')
    })

    it('never says NPC, first token, GPU layers or context length', () => {
      for (const stage of ['waiting', 'reading', 'writing', 'finishing', 'checking', 'voice'] as const) {
        const { unmount } = render(
          <NpcTurnProgress active elapsedMs={65_000} estimateMs={40_000} npcName="Dana" stage={stage} prompt={{ processed: 1, total: 2, cached: 0 }} replyStart={{ lowMs: 5_000, highMs: 8_000 }} />,
        )
        const text = document.body.textContent ?? ''
        expect(text).not.toMatch(/\bNPC\b/)
        expect(text).not.toMatch(/first token|GPU layers|context length/i)
        unmount()
      }
    })

    it('rests focus on the panel while the turn is out', () => {
      renderStage({ stage: 'reading' })
      expect(document.activeElement).toBe(screen.getByTestId('npc-turn-progress'))
    })

    it('announces "Your turn." once the turn has landed', () => {
      const { rerender } = renderStage({ stage: 'reading' })
      rerender(<NpcTurnProgress active={false} elapsedMs={0} estimateMs={40_000} npcName="Dana" stage={null} yourTurn />)
      expect(screen.getByTestId('npc-turn-progress-status')).toHaveTextContent('Your turn.')
      expect(screen.queryByTestId('npc-turn-progress')).not.toBeInTheDocument()
    })

    it('offers no control: the demo shows this panel and nothing it cannot do', () => {
      renderStage({ stage: 'reading', replyStart: { lowMs: 5_000, highMs: 8_000 } })
      expect(screen.getByTestId('npc-turn-progress').querySelectorAll('button, a, input')).toHaveLength(0)
    })

    it('passes axe in every state', async () => {
      const states: Array<Partial<NpcTurnProgressProps>> = [
        { stage: 'waiting' },
        { stage: 'reading', prompt: { processed: 512, total: 2048, cached: 128 }, replyStart: { lowMs: 5_000, highMs: 8_000 } },
        { stage: 'writing', streaming: true },
        { stage: 'checking' },
        { stage: null, estimateMs: null },
        { stage: null, estimateMs: 30_000, elapsedMs: 50_000 },
      ]
      for (const state of states) {
        const { container, unmount } = render(
          <NpcTurnProgress active elapsedMs={3_000} estimateMs={40_000} npcName="Dana" {...state} />,
        )
        const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
        expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(', ')}`)).toEqual([])
        unmount()
      }
    })
  })

  describe('the reply-speed footnote (issue #501 §1)', () => {
    // A playtester hit a slow turn, left to find a speed setting, and lost the
    // session. The footnote names the setting where the wait is felt, as text
    // and never a link, and says it applies from the next reply. Issue #539
    // moved it from a notice of its own into the panel, which already says who
    // the player is waiting on, so the footnote says nothing about the wait.
    it('appears once the wait passes five seconds, as text and not a link', () => {
      const { unmount } = renderProgress(4_000, null)
      expect(screen.queryByTestId('slow-response-indicator')).not.toBeInTheDocument()
      unmount()

      renderProgress(6_000, null)
      const notice = screen.getByTestId('slow-response-indicator')
      const hint = screen.getByTestId('slow-response-speed-hint')
      expect(screen.getByTestId('npc-turn-progress')).toContainElement(notice)
      expect(hint).toHaveTextContent(/reply speed/i)
      expect(hint).toHaveTextContent(/settings/i)
      expect(hint).toHaveTextContent(/once this reply arrives/i)
      expect(notice.querySelectorAll('a, button')).toHaveLength(0)
      // The heading and the announcement already say the turn is running long.
      expect(notice).not.toHaveTextContent(/taking longer than usual/i)
    })

    it('stays with the stages the core reports, which say nothing about speed', () => {
      render(
        <NpcTurnProgress active elapsedMs={6_000} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed: 1, total: 4, cached: 0 }} />,
      )
      expect(screen.getByTestId('slow-response-speed-hint')).toHaveTextContent(/reply speed/i)
    })

    it('offers the demo its one hardware lever beside the setting, and the full app nothing extra', () => {
      const { unmount } = render(<NpcTurnProgress active elapsedMs={6_000} estimateMs={null} demo />)
      expect(screen.getByTestId('slow-response-indicator')).toHaveTextContent(/closing other apps usually helps/i)
      expect(screen.getByTestId('slow-response-speed-hint')).toHaveTextContent(/reply speed/i)
      unmount()

      renderProgress(6_000, null)
      expect(screen.getByTestId('slow-response-indicator')).not.toHaveTextContent(/closing other apps/i)
    })

    it('is announced through a region that was mounted before the sentence arrived', () => {
      // The footnote used to be a status region mounted at five seconds with
      // its sentence already inside: the pattern a screen reader may never
      // announce. Its sentence now arrives in a region that has been there,
      // empty, since before the turn went out.
      const { rerender } = render(<NpcTurnProgress active={false} elapsedMs={0} estimateMs={null} demo />)
      const region = screen.getByTestId('npc-turn-progress-hint')
      expect(region).toHaveAttribute('role', 'status')
      expect(region).toHaveTextContent('')
      rerender(<NpcTurnProgress active elapsedMs={4_000} estimateMs={null} demo />)
      expect(region).toHaveTextContent('')
      rerender(<NpcTurnProgress active elapsedMs={6_000} estimateMs={null} demo />)
      expect(screen.getByTestId('npc-turn-progress-hint')).toBe(region)
      expect(region).toHaveTextContent(/^Closing other apps usually helps\. Once this reply arrives, you can shorten the next ones under Reply speed, in Settings\.$/)
      // The visible footnote is hidden like the rest of the panel, so the
      // sentence is heard once.
      expect(screen.getByTestId('slow-response-indicator')).toHaveAttribute('aria-hidden', 'true')
      rerender(<NpcTurnProgress active={false} elapsedMs={0} estimateMs={null} demo />)
      expect(region).toHaveTextContent('')
    })
  })

  describe('motion', () => {
    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('animates the fill unless the player asked for less motion', () => {
      vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
      render(<NpcTurnProgress active elapsedMs={3_000} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed: 1, total: 4, cached: 0 }} />)
      expect(screen.getByTestId('npc-turn-progress-fill').getAttribute('style')).toContain('transition: width')
    })

    it('opens the reading bar at the share read, not by sweeping back from the full-width hatch', () => {
      // jsdom runs no transitions, so the mechanism is what gets pinned. A
      // transition runs from an element's old width to its new one: had the
      // hatch's element (100% wide) become the fill, every reading stage would
      // open with a full emerald bar shrinking to 25%. A new element is
      // painted at its first width.
      vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
      const reading = (processed: number) => (
        <NpcTurnProgress active elapsedMs={1_000} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed, total: 2048, cached: 0 }} />
      )
      const { rerender } = render(<NpcTurnProgress active elapsedMs={1_000} estimateMs={null} npcName="Dana" stage="waiting" />)
      const hatch = screen.getByTestId('npc-turn-progress-fill')
      expect(hatch).toHaveStyle({ width: '100%' })
      rerender(reading(512))
      const fill = screen.getByTestId('npc-turn-progress-fill')
      expect(fill).toHaveStyle({ width: '25%' })
      expect(fill).not.toBe(hatch)
      // Within the stage it is the same element, so the bar animates forwards.
      rerender(reading(1024))
      expect(screen.getByTestId('npc-turn-progress-fill')).toBe(fill)
      expect(fill).toHaveStyle({ width: '50%' })
    })

    it('does not animate under prefers-reduced-motion', () => {
      vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
      render(<NpcTurnProgress active elapsedMs={3_000} estimateMs={null} npcName="Dana" stage="reading" prompt={{ processed: 1, total: 4, cached: 0 }} />)
      const style = screen.getByTestId('npc-turn-progress-fill').getAttribute('style') ?? ''
      expect(style).toContain('transition: none')
      expect(style).not.toMatch(/animation/)
    })
  })
})
