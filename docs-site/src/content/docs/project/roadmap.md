---
title: "Roadmap"
description: "MVP acceptance criteria, build order, current status, deferred future work, and explicit non-goals for Conversation Simulator."
sidebar:
  order: 1
---

> **Purpose of this document:** Keep contributors focused on the breakthrough —
> local extensible conversation simulation — not on scope that would compromise
> that focus. If a proposal fits this document's MVP criteria, it belongs here.
> If it belongs in a "not now" section, it should wait.

---

## MVP acceptance criteria

A build qualifies as MVP when **every item below is true**:

1. A player can open a scenario, have a complete text conversation with an NPC, and reach a scored debrief — entirely offline, on a mid-spec laptop.
2. Scenario packs are plain YAML. A non-programmer can fork and edit one without writing code.
3. The schema validator catches malformed packs at import time and prints an actionable error.
4. At least one official scenario pack ships with four distinct, playable scenarios.
5. Voice input (Whisper STT) and voice output (Kokoro / sherpa-onnx TTS) work as opt-in features on the same local machine.
6. A workbench UI lets a contributor inspect live state, replay a turn, and validate a pack without touching the CLI.
7. No outbound network call is made during play. The [offline smoke test](/trust/privacy/) exits zero.
8. The README and docs are accurate enough that a new contributor can run the project from `git clone` to first conversation in under 15 minutes.

---

## Build order

Work proceeds in this sequence. Later items depend on earlier items shipping and
being stable. Do not start an item before its predecessor passes its acceptance
criteria.

| # | Item | Why first |
|---|------|-----------|
| 1 | **Text conversation loop** | Everything else is UI on top of this |
| 2 | **Schema / validator** | Pack authors need a contract before writing content |
| 3 | **One excellent scenario** | Proves the loop works end-to-end with real content |
| 4 | **Model manager** | Stable download + version-lock before adding more dependencies |
| 5 | **Voice input (Whisper STT)** | Adds a new input mode without changing the core loop |
| 6 | **Voice output (Kokoro / sherpa-onnx TTS)** | Closes the full local audio loop |
| 7 | **Workbench UI** | Tooling for contributors; requires stable loop and schema |
| 8 | **More official packs** | Content diversity once the system is proven |
| 9 | **README / demo polish** | Final surface for GitHub launch |

---

## Status

> Live status lives on the **[delivery board](https://github.com/orgs/outrightmental/projects/12)** — every issue this project has ever
> shipped, organized into phases, with the open backlog extending from there. The
> snapshot below is narrative; the board is the record.

### Next — v1.0 Paid launch (milestone due Nov 28, 2026)

The $9.99 Steam edition goes live. Grouped by what it changes for the player:

- **Replies start sooner:** each turn's prompt extends the last (#524), the prompt is read ahead while the player types (#525), less is read and written per turn (#543), and one honest speed definition replaces the conflicting targets (#522, #520)
- **The engine fits the machine:** settings take effect (#529), the graphics card by default with a processor fallback (#530, #531, #532), the engine tunes itself (#521, #535, #536), and Ollama gets the selected model (#528)
- **Turns never go wrong twice:** a turn never runs twice and keeps the player's words on failure (#541), a reply can be stopped (#540), output repair is non-blocking and the output check stops rejecting innocent lines (#526, #527)
- **Reply speed is the player's choice:** one control with plain presets, changeable mid-conversation and shown before the start (#546, #547, #548)
- **Voice works in the packaged builds:** audio plays on all three platforms and never delays the text (#533, #534), and the voice models install from onboarding (#487)
- **A real-model gate in CI:** the nightly conversation runs the engine players run and gates turn-speed regressions (#457, #542)
- **Store and business:** the $9.99 registration and premium DLC (#361, #364, #366), the real store URL on the download page (#362), the full achievement set (#494)
- **Housekeeping before launch:** everything the app writes under the data root (#562), the Windows developer setup (#564), First Words defined once (#553)
- **Launch epics:** public beta readiness (#315) and the signature experience (#316)

### Then — v1.1 Post-launch (milestone due Jan 16, 2027)

Auto-update (#461), the accessibility audit (#462), performance targets on reference hardware (#463), voice setup from the Model Manager (#464), the community pack browser and pack signing (#465, #466), Flyting (#454), NPCs that escalate and eject a saboteur (#552), an Intel build of the macOS depot (#575), short model names (#555), what this computer can run (#537), per-reply speed (#549), voice that starts mid-reply (#544), the debrief as a continuation of the conversation (#545), the turn-speed epic (#518), and small setup inconsistencies (#566).

### Done — shipped in v0.4.0

- [x] The reply arrives as it is written: sentence-by-sentence streaming over a WebSocket served by convsim-core, with released text committed (#538)
- [x] The wait says what it is doing: staged turn panel, reading bar, reply-start estimate from this machine's measured speeds (#539)
- [x] Every turn records what it cost: engine timings, stage times, extra calls, rolling speeds endpoint (#519)
- [x] The engine launches for one conversation: one slot, registry context size, 256-token batches, 1 GiB prompt cache bound (#523)
- [x] The first session explains itself: resume, reply speed, plain wording, meter clarity, whole-turn counting (#501)
- [x] The Conversation Brief leads with the mission: numbered goals, two decisions, the mechanical settings in one card (#500, building on #486)
- [x] The demo has its own icon set and Steamworks icons (#499)
- [x] Copy diagnostics works on macOS; a rejected request names the field (#508)
- [x] Model downloads show the real model folder and offer Retry when the connection drops (#568)
- [x] Slow turns wait instead of failing; convsim-core runs as a supervised sidecar and shuts down its whole process tree (#489, #456, #485)
- [x] Screenshots and a demo recording from a real local-model session (#455); diagnostics name the release version (#490); tracker structure declared and validated in CI (#491)
- [x] The store copy, QA matrix, depot template and publishing docs say the macOS build is Apple Silicon only, and CI fails if they claim Intel again (#563; Intel tracked in #575)
- [x] README, website and docs stop stating a pack count that drifts, stop claiming Steam Deck Verified, name the AppImage the build produces, and describe the desktop app's data folder (#565)
- [x] Screenshots and the README demo recording recaptured from a real local-model session on the v0.4 conversation screen (#554)
- [x] The free demo edition — one model, five curated conversations, its own Steam app — is built from this release (#495)

### Done — the v0.3 onboarding overhaul (shipped through v0.2.x; v0.3.0 was never tagged)

- [x] Onboarding overhaul — first conversation in 60 seconds, zero error walls (#388)
  - Welcome screen: "Set me up" vs "Try it right now" (two-card, one decision)
  - Play while it downloads: scripted tutorial starts in < 15 s, real model arrives in background
  - One-click resumable install pipeline (engine → model → verify → warmup → packs)
  - Windows native engine provisioning — no WSL2 required
  - Self-healing checks: auto-fixable failures silent, remediation cards only for genuine user decisions
  - Dead-loop fixed: no fix action ever redirects back to Welcome
  - Server-authoritative setup state (`GET /api/setup/status`)
  - Voice invite deferred to after first real AI conversation
  - Setup docs describe the actual shipped UI; CI drift-prevention check enforces it
  - Onboarding e2e suite (P1–P8 wiped-profile journeys) as merge and release gate

### Done — shipped in v0.1.0-alpha.1

- [x] Monorepo skeleton — directory structure, licensing, tooling
- [x] Developer scripts (`setup.sh`, `dev.sh`, PowerShell equivalents)
- [x] Model registry with checksums and explicit license disclosure flow
- [x] Local TTS adapter (Kokoro / sherpa-onnx, synthetic voices, no voice cloning)
- [x] Text-only workbench — chat panel + live state inspector
- [x] Four official packs — Job Interview Basics, Everyday Negotiation, Language Café, Difficult Conversations (four playable scenarios each)
- [x] README rewritten for instant GitHub comprehension
- [x] Core conversation loop: player turn → LLM inference → NPC response → state update
- [x] Debrief generation from rubric scores
- [x] Browser UI connected to Python backend via WebSocket
- [x] JSON Schema covering scenarios, NPCs, rubrics, scenes, safety policies
- [x] Pack validator CLI (`convsim validate-pack <path>`)
- [x] Pack import/export flow in the browser workbench
- [x] Offline smoke test CI gate
- [x] Whisper STT integration (voice input, local — requires whisper.cpp runtime)
- [x] Full TTS playback connected to scenario engine (Kokoro — requires local server)
- [x] Workbench: state inspector, pack editor, validation, export
- [x] Layered safety system with global non-overridable rules and per-pack policies
- [x] Cross-platform CI pipeline with acceptance tests, pack validation, and release smoke matrix
- [x] Contribution guide, code of conduct, security policy, issue templates
- [x] Full documentation set (architecture, install, safety, privacy, scenario authoring, troubleshooting)

### Remaining polish — before Milestone 1 tag

- [x] Real UI screenshots and demo recording, captured from a local-model playthrough
- [x] Desktop app with bundled backend (Tauri sidecar for `convsim-core`)
- [ ] Automated real-model CI smoke test

### Post-alpha — Milestone 2+

See the [post-alpha issues list](/dev/post-alpha-issues/) for the full
triaged list with reasons and milestone assignments.

---

## Future work — outside MVP, not forgotten

These areas are intentionally **out of scope for MVP**. They are listed here so
contributors know they have been considered and deferred, not overlooked.

Recording them here does **not** create a commitment to build them. Any future
work in these areas needs its own proposal, design, and acceptance criteria.

### Visual upgrades

- Animated NPC avatars or portrait art
- Scene backgrounds and atmospheric overlays
- Custom fonts, themes, or visual design systems beyond the base UI

### Advanced conversation features

- Multi-NPC scenes (more than one NPC active at once)
- Branching dialogue trees with author-defined decision nodes
- Long-term memory across sessions (persistent relationship state)
- Emotion-to-voice prosody mapping (anger, warmth, uncertainty in TTS)

### UGC ecosystem

- In-app pack browser / discovery feed
- Community ratings and reviews
- Pack signing and trust tiers
- Hosted pack registry (CDN or P2P distribution)

See the [marketplace architecture](/dev/marketplace-architecture/) for the post-launch marketplace design baseline — entry gate criteria, distribution path comparison, and scope of schema, signing, moderation, payment, and reporting changes required before any paid content ships.

### Education and enterprise

- Classroom dashboard (instructor sees student session aggregates)
- LMS integration (SCORM / xAPI export)
- Analytics and cohort reporting
- Enterprise SSO or managed deployment

---

## Not now

The following are explicitly **out of scope** and should not be proposed as MVP
additions. A future proposal can revisit them, but the bar is high: any yes
must not compromise offline-first, local-model, or open-source principles.

| Topic | Why not now |
|-------|-------------|
| **VR / AR** | Requires platform-specific SDKs, hardware, and a whole second rendering stack — incompatible with MVP simplicity |
| **Multiplayer** | Server infrastructure, latency, identity — all the things MVP deliberately avoids |
| **Cloud inference** | Contradicts the local-first promise; would require an account and send user content to a third party |
| **Mobile apps** | App store rules, on-device model size, and touch UI are a separate product effort |
| **Marketplace / monetization** | Payment rails, refund policy, fraud, curation burden — not a developer tool concern |
| **NSFW content** | Above PG-13 is a hard platform boundary; the safety system enforces this at the validator level |
| **Celebrity or public-figure packs** | Defamation, right-of-publicity, and likeness risk with no upside for the simulator's core use case |
| **Complex character animation** | Requires a game-engine-class renderer; out of proportion for a conversation tool |
| **Therapy / law / medical positioning** | These are licensed professions; shipping a product that implies clinical efficacy creates liability without benefit |

---

## Links

- [Acceptance criteria](/reference/spec/#24-mvp-acceptance-criteria) — the player, creator, developer, and concept tests that gate the MVP
- [Architecture](/reference/architecture/) — service layout and port assignments
- [Scenario authoring guide](/create/scenario-authoring/) — how to write a pack
- [Pack validation](/create/pack-validation/) — schema rules and the validator CLI
- [Safety policy](/trust/safety-policy/) — content boundaries and the layered safety system
- [Privacy and data policy](/trust/privacy/) — what stays local and how to verify it
- [Steam edition roadmap](/dev/steam-roadmap/) — release principles, release train, and platform targets for the paid ($9.99) Steam edition
- [Steam MVP scope and release gates](/dev/steam-mvp-scope/) — minimum playable release features, optional targeted features, pass/fail gates, and post-launch deferrals
- [GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones) — issue tracking
- [Full specification](/reference/spec/) — technical requirements per milestone
