<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Conversation Simulator

> Flight Simulator for conversations.

A local-first, open-source simulator for practicing interviews, negotiations,
language conversations, and difficult social situations with AI NPCs running
on your own computer.

---

## What is this?

Choose a scenario. Talk naturally. The NPC reacts. The situation evolves.
Review what happened. Remix the scenario.

Every conversation runs **100% on your computer** — no cloud inference, no
transcription API calls, no telemetry.

```
Scenario: Hostile Executive Interview
Player:   "I think my background in product operations prepares me well..."
NPC:      "That sounds broad. Give me one measurable result."
State:    pressure +8 | patience -3 | specificity challenge triggered
```

---

## First implementation target

The first milestone is a **text-only local simulator** — no voice, no desktop
packaging yet. The scenario engine, structured NPC output, local model
integration, and debrief loop come first. Voice input (Whisper) and Tauri
desktop packaging come in later milestones.

See the [full spec](docs/SPEC.md) and the
[GitHub milestones](https://github.com/outrightmental/ConversationSimulator/milestones)
for the build order.

---

## Developer quickstart

### Requirements

- Python 3.10+
- Node.js 18+
- npm or pnpm

### Setup

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh
```

The setup script checks your environment, installs frontend packages, creates
the Python virtual environment for `convsim-core`, and creates local data
directories under `~/.convsim/`. It does **not** modify global state or
download model files.

On Windows (PowerShell), use `scripts\setup.ps1` instead.

### Start local dev

```bash
./scripts/dev.sh
```

This starts both services and prints their URLs. Press **Ctrl-C** to stop
everything cleanly.

| Service       | URL                   | Responsibility              |
| ------------- | --------------------- | --------------------------- |
| convsim-ui    | http://127.0.0.1:7354 | Browser UI (dev mode)       |
| convsim-core  | http://127.0.0.1:7355 | Main server, API, WebSocket |
| convsim-llm   | http://127.0.0.1:7356 | Local LLM server            |
| convsim-stt   | http://127.0.0.1:7357 | Speech-to-text worker       |
| convsim-tts   | http://127.0.0.1:7358 | Text-to-speech worker       |

Runtime logs are written to `~/.convsim/logs/` (override with
`CONVSIM_LOG_DIR`). If a port is already occupied the script reports which
process is blocking it.

On Windows (PowerShell), use `scripts\dev.ps1` instead.

---

## Local-first promise

> Conversation Simulator does not send your conversations, audio, prompts,
> transcripts, or model outputs to any server during play. Model and pack
> downloads happen only when you explicitly request them.

**What this means in practice:**

- LLM inference, speech-to-text, and text-to-speech all run on local models —
  no cloud API calls during a session.
- Transcripts are stored in a local SQLite database only when you opt in.
- Raw audio is never saved by default — only the transcribed text is processed.
- TTS-synthesized audio is cached locally. Nothing is sent to external servers.
- **Telemetry is absent from the MVP.** No usage data, analytics, or crash
  reports are transmitted. There is no opt-in or opt-out telemetry switch.
- All services bind to `127.0.0.1` so no ports are reachable from other machines.

See [`docs/privacy.md`](docs/privacy.md) for the full data-handling policy,
including what is logged, how to export your data, and how to delete everything.

You can verify the local-only guarantee at any time with the built-in offline
smoke test:

```bash
# Run against an official pack (no model download needed)
npx convsim offline-smoke-test packs/official/job-interview-basic

# Run with machine-readable output (for CI)
npx convsim offline-smoke-test --json packs/official/job-interview-basic
```

The command loads the first scenario from the pack, runs a scripted
conversation with a fake runtime, generates a local debrief, and confirms
that no outbound TCP connection was attempted during play.  It exits
**nonzero with an actionable error** if any subsystem (LLM inference, STT,
TTS, telemetry, asset fetch) reaches out to an external host.

---

## Repository layout

```
apps/
  desktop/       Tauri desktop wrapper (future)
  web/           React/TypeScript browser UI

packages/
  ui/            Shared UI component library
  scenario-schema/   TypeScript types for scenario packs
  shared-types/  Shared TypeScript types across apps

services/
  convsim-core/  Python FastAPI server — scenario engine, API, WebSocket

runtimes/
  llama_cpp/     llama.cpp integration and binary management
  whisper_cpp/   whisper.cpp integration for local speech-to-text

packs/
  official/      First-party scenario packs (CC BY 4.0)
    job-interview-basic/
    everyday-negotiation/
    language-cafe/
    difficult-conversations/

schemas/         JSON schemas for packs, scenarios, NPCs, rubrics
model-registry/  Curated registry of supported local models
docs/            Documentation (CC BY 4.0) — start with docs/SPEC.md
scripts/         Developer setup and launch scripts
```

---

## Starter scenarios (planned)

| Pack                    | Scenarios                                          |
| ----------------------- | -------------------------------------------------- |
| Job Interview Basics    | Behavioral, hostile executive, blue-collar, stretch |
| Everyday Negotiation    | Used car, lease renewal, freelance, customer service |
| Language Café           | Spanish, French, Japanese, English small talk      |
| Difficult Conversations | Feedback, apology, boundary, raise request         |

---

## Licensing

| Content                 | License    |
| ----------------------- | ---------- |
| Application code        | Apache-2.0 |
| Official scenario packs | CC BY 4.0  |
| Placeholder assets      | CC0-1.0    |
| Documentation           | CC BY 4.0  |
| Model weights           | Not bundled; user downloads with license disclosure |

See `LICENSE` for the full Apache-2.0 text.
See `NOTICE` for copyright notices and per-artifact license details.
