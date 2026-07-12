<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Brand guide: Conversation Simulator

## Positioning statement

Conversation Simulator is the simulator for conversations.

## Named niche

Aspiring conversationalists and negotiators: people preparing for job interviews,
salary negotiations, difficult feedback, language practice, and any high-stakes
conversation where rehearsal makes the difference.

## Boilerplate copy

### 10-word

The simulator for interviews, negotiations, language, and difficult conversations.

### 50-word

Conversation Simulator is the practice tool for high-stakes conversations. Choose
a scenario, talk to an AI character that runs entirely on your computer, watch the
situation evolve, and review what went well — then run it again. Interviews,
negotiations, language practice, difficult discussions — all offline, all private.

### 200-word

Conversation Simulator is the simulator for conversations. It is the dedicated
practice environment for aspiring conversationalists and negotiators: people who
want to rehearse a job interview before they walk into the room, negotiate a raise
before it matters, hold a difficult conversation before they have to hold the real
one.

Choose a scenario from the built-in packs — job interviews, salary negotiations,
everyday negotiation, language practice, or difficult discussions. Talk to an AI
character whose reactions evolve as the conversation unfolds. When you finish,
review a scored debrief: what you said clearly, where you hedged, and the moments
that changed the dynamic.

Everything runs on your computer. No cloud inference, no account, no subscription.
An internet connection is only needed for the one-time model download. Once
installed, the app runs entirely offline — your conversations never leave your
machine.

Conversation Simulator is free and open-source — $9.99 on Steam, free to build
from source, with premium expansion packs on Steam. Build your own scenario packs
in YAML, share them with other players, or extend the platform with new runtimes
and rubrics.

---

## Visual identity

The identity has one story: **two voices on a dark stage.** Everything else
derives from it.

### The mark — "The Exchange"

Two speech bubbles mid-turn: violet underneath (the player, speaking up),
emerald above (the character, replying). Source: `docs/assets/brand/mark.svg`.
It is the favicon of the app, the website, and the docs site. Don't recolor
it, don't separate the bubbles, don't add a third.

### The two voices (palette)

The colour system is the product's own transcript colour coding, promoted to
brand. Use the CSS custom properties in `apps/web/src/index.css`.

| Token | Hex | Role |
|-------|-----|------|
| `--cs-you` / deep / dim | `#a78bfa` / `#7c5cdb` / `#1e1b4b` | **You** — the player's voice. Primary actions, links, focus rings. |
| `--cs-them` / deep / dim | `#6ee7b7` / `#10b981` / `#052e16` | **Them** — the character's voice. NPC labels, positive/ready state. |
| `--cs-event` / dim | `#fbbf24` / `#1c0a00` | **The moment** — scenario events, turning points, warnings. |
| `--cs-stage` / deep / raise | `#0f0f11` / `#09090b` / `#18181b` | **The stage** — background surfaces, darkest to raised. |
| `--cs-border` | `#27272a` | Hairlines and card borders. |
| `--cs-text` strong/base/muted/faint | `#f4f4f5` / `#e8e8ea` / `#a1a1aa` / `#71717a` | Type ramp. On marketing surfaces, keep small informative text at `#8b8b94` or lighter for WCAG AA. |

Violet always means the player; emerald always means the character. Never
swap them, and never use either as mere decoration where the you/them
meaning could confuse.

### Typography

- **Display ("the playbill")**: [Fraunces](https://github.com/undercasetype/Fraunces)
  (SIL OFL 1.1) — headlines and the wordmark on the website and docs site.
  Warm, literary, a little theatrical; optical sizing on. The hero headline
  may switch the WONK axis on. Self-hosted (`website/static/fonts/`,
  `docs-site/public/fonts/`); never loaded from a third-party CDN.
- **UI & body ("the instrument")**: the system stack
  (`system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`) — everything
  in the app, and body text everywhere. Fast, native, offline-true.
- **Stage directions**: the system mono stack, uppercase, letter-spaced —
  micro-labels like `TURN 4 · NPC` and `SCENARIO EVENT`. This is the
  identity's signature texture; use it for meter names, turn labels, and
  data callouts.

### Motifs

- **The transcript card**: a conversation exchange with you/them colour
  coding is the brand's hero image — prefer it over abstract illustration.
- **State meters**: thin rounded bars in the voice colours. The number shown
  always matches the fill.
- **The wordmark** is set in Fraunces alongside the mark; the name is always
  written out in full — "Conversation Simulator", never "ConvSim" in
  user-facing surfaces (`convsim` survives only in code and CLI names).

## Tone guide

**Authoritative, warm, concrete.** Conversation Simulator owns its category. It
does not compare itself to other genres or apologise for what it is. It speaks
directly to the player about what they will do and why it matters.

### Do

| ✓ Do | Why |
|------|-----|
| "Conversation Simulator is the simulator for conversations." | Owns the category directly — no apology, no analogy. |
| "Practice the conversation before it matters." | Concrete, action-oriented, addresses the real need. |
| "Your conversations stay on your machine — no cloud, no account, no subscription." | Specific and factual; privacy as a strength, not a disclaimer. |

### Don't

| ✗ Don't | Why |
|---------|-----|
| "It's like a flight simulator, but for conversations." | Borrows authority from another genre. We are the category, not a derivative of one. |
| "Think of it as a chatbot you can practise with." | Undersells the structured scenario system; invites chatbot comparisons we don't want. |
| "We hope this helps you improve your conversations." | Apologetic hedging. State what the tool does, not what you hope it does. |
