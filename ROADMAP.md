<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Roadmap

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
7. No outbound network call is made during play. The [offline smoke test](docs/privacy.md) exits zero.
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

### Done

- [x] Monorepo skeleton — directory structure, licensing, tooling
- [x] Developer scripts (`setup.sh`, `dev.sh`, PowerShell equivalents)
- [x] Model registry with checksums and explicit license disclosure flow
- [x] Local TTS adapter (Kokoro / sherpa-onnx, synthetic voices, no voice cloning)
- [x] Text-only workbench — chat panel + live state inspector
- [x] Job Interview Basics official pack — four playable scenarios
- [x] README rewritten for instant GitHub comprehension

### In progress — Milestone 1 (text conversation loop)

- [ ] Core conversation loop: player turn → LLM inference → NPC response → state update
- [ ] Debrief generation from rubric scores
- [ ] Browser UI connected to Python backend via WebSocket

### Next — Milestone 2 (schema, validator, pack tooling)

- [ ] JSON Schema covering scenarios, NPCs, rubrics, scenes, safety policies
- [ ] Pack validator CLI (`npx convsim validate-pack <path>`)
- [ ] Pack import flow in the browser workbench
- [ ] Offline smoke test CI gate

### After that — Milestones 3–5

- [ ] Whisper STT integration (voice input, local, no audio uploads)
- [ ] Full TTS playback connected to scenario engine (voice output)
- [ ] Workbench: turn replay, state diff, rubric live preview
- [ ] Everyday Negotiation, Language Café, Difficult Conversations packs
- [ ] Polished demo GIF and README launch assets

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

- [Acceptance criteria](docs/SPEC.md#24-mvp-acceptance-criteria) — the player, creator, developer, and concept tests that gate the MVP
- [Architecture](docs/architecture.md) — service layout and port assignments
- [Scenario authoring guide](docs/scenario-authoring.md) — how to write a pack
- [Pack validation](docs/pack-validation.md) — schema rules and the validator CLI
- [Safety policy](docs/safety-policy.md) — content boundaries and the layered safety system
- [Privacy and data policy](docs/privacy.md) — what stays local and how to verify it
- [GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones) — issue tracking
- [Full specification](docs/SPEC.md) — technical requirements per milestone
