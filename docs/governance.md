<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Governance: how this project is run

Conversation Simulator is maintained by [Outright Mental](https://outrightmental.com) with
an unusual crew: one human maintainer, an autonomous issue-to-PR factory
([vibrator](https://github.com/outrightmental/vibrator)), and a community of contributors.
This document is the operating manual — where decisions are made, how work flows, and the
rules that keep the record trustworthy. The tracker and board were consolidated into this
shape on 2026-08-21.

For *why* the project is shaped this way — lineage, competitive landscape, and the
economics — see [landscape.md](landscape.md).

---

## Decision rights

- **Final call:** the Outright Mental maintainer ([@charneykaye](https://github.com/charneykaye)).
  Benevolent-dictator model; scope discipline per [ROADMAP.md](../ROADMAP.md) ("Not now"
  is a real list, and it is enforced).
- **Proposals:** open an issue. Feature proposals use the issue forms; anything in
  ROADMAP's "Future work" needs its own proposal, design, and acceptance criteria before
  implementation.
- **Conduct:** [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).
  **Security:** [SECURITY.md](../SECURITY.md) — private reporting, no public zero-days.

---

## The delivery board

**[github.com/orgs/outrightmental/projects/12](https://github.com/orgs/outrightmental/projects/12)**
is the single pane of glass: every issue ever shipped and everything still to come — one
record, in phases.

| View | What it shows |
| ---- | ------------- |
| **Board** | Open work by Status (Todo → In Progress → Done) |
| **Priorities** | Open work grouped P0 → P2; untriaged items surface with no priority |
| **Timeline** | The entire history as a roadmap — every item with real start/finish dates |
| **History** | Every phase and everything shipped in it |

Work is organized into **phases** — append-only eras of the project's life:

| Phase | Span | Items | What happened |
| ----- | ---- | ----- | ------------- |
| 01 · Alpha build | Jun 30 – Jul 8, 2026 | 85 | Empty repo → complete local MVP (engine, packs, voice, safety, workbench) — `v0.1.0-alpha.1` |
| 02 · Steam release | Jul 9 – 11 | 62 | Store, depots, signing, platform QA (the closed *Steam Release Roadmap* milestone) |
| 03 · Beta & signature | Jul 10 – 11 | 23 | Public-beta readiness ([#315](https://github.com/outrightmental/ConversationSimulator/issues/315)) and signature-experience ([#316](https://github.com/outrightmental/ConversationSimulator/issues/316)) programs |
| 04 · Pivot & onboarding | Jul 11 – 13 | 24 | FOSS/$9.99 business-model pivot ([#366](https://github.com/outrightmental/ConversationSimulator/issues/366)) and the v0.3 onboarding overhaul ([#388](https://github.com/outrightmental/ConversationSimulator/issues/388)) |
| 05 · Hardening | Jul 13 – Aug 5 | 13 | Signing chains, release dress rehearsals, post-v0.3 fixes |
| 06 · Release polish | now | — | What remains before the Milestone-1 tag |
| 07 · Future | — | — | Groomed post-launch backlog (see [post-alpha-issues.md](post-alpha-issues.md)) |

Board automations: new issues add themselves; closing an issue moves it to **Done**;
reopening returns it to **Todo**; a linked PR moves it to **In Progress**. The Priority
field mirrors the `priority:*` labels.

---

## Labels, types, and milestones

Three orthogonal systems, each answering one question:

- **Labels** — what/where/how urgent. Four axes, 18 labels total, documented in
  [CONTRIBUTING.md → Labels](../CONTRIBUTING.md#labels). Do not invent labels ad hoc.
- **Native issue types** (Bug / Feature / Task) — what kind of work, machine-readable.
  The factory prioritizes `Bug` first.
- **Milestones** — release trains (*when*). The board's Phase field records *eras*, not
  deadlines; milestones carry deadlines.

---

## The factory

[vibrator](https://github.com/outrightmental/vibrator) turns the issue queue into a
self-driving implementation pipeline:

1. An issue is filed and triaged (type, labels, priority — see above).
2. Unless it carries the **`manual`** label, vibrator may pick it up — ordered by
   Type = Bug first, then earlier milestone, then age — respecting `blocked by #N` /
   sub-issue dependencies.
3. It implements on a `vibrator/issue-N-…` branch and opens a PR; CI gates it; a human
   squash-merges.

The two contract labels:

- **`manual`** — humans only; the factory never touches it. Applied to anything requiring
  real-world action (Steamworks registration, hardware capture), business judgment, or
  deliberate sequencing.
- **`review`** — the factory implements, but the final PR review is explicitly human.

**The throttle:** items in *07 · Future* are filed with `manual` on. Releasing one to the
factory is a single act — remove `manual`. That keeps the backlog groomed and deep without
the factory building post-launch features prematurely.

---

## Keeping the record honest

- **Every deferral has an issue.** [post-alpha-issues.md](post-alpha-issues.md) items each
  link a tracking issue; when something ships, its entry is updated or removed. No silent
  scope changes.
- **Phases are append-only.** Closed eras on the board are history — do not relabel or
  rewrite them.
- **Docs describe shipped reality.** Setup docs must match the shipped UI (CI-enforced
  since v0.3). Aspirational docs live in proposals, not in `docs/`.
- **The board stays public.** Visible momentum — 219 items and counting, seven weeks from
  empty repo to signed Steam-ready build — is both accountability and marketing.

---

## The commercial engine

The money model, in one breath (details:
[README → How it's distributed](../README.md#how-its-distributed) ·
[DLC_MODEL.md](DLC_MODEL.md) · precedents: [landscape.md](landscape.md#business-model-precedents)):

**Free engine on GitHub** (Apache-2.0, four official packs CC BY 4.0) → **$9.99 Steam
edition** selling packaging — signed, notarized, auto-updating, Deck-verified — →
**first-party premium pack DLC** from a private repo. Revenue funds development. Two
invariants protect the compact: the open core never shrinks, and every edition keeps the
same local-first guarantee — no account, no cloud, no telemetry.

---

## Cadence

- **Release trains** follow [STEAM_ROADMAP.md](STEAM_ROADMAP.md) stages, with the
  [release checklist](release-checklist.md) and dress-rehearsal workflow.
- **Nightly** real-model smoke ([#457](https://github.com/outrightmental/ConversationSimulator/issues/457))
  guards inference quality once landed.
- **Each release:** sweep this document, [landscape.md](landscape.md), and
  [post-alpha-issues.md](post-alpha-issues.md) for drift.
