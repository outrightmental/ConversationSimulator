[![CI](https://github.com/outrightmental/ConversationSimulator/actions/workflows/ci.yml/badge.svg)](https://github.com/outrightmental/ConversationSimulator/actions/workflows/ci.yml)
[![Release](https://github.com/outrightmental/ConversationSimulator/actions/workflows/release.yml/badge.svg)](https://github.com/outrightmental/ConversationSimulator/actions/workflows/release.yml)

<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Conversation Simulator

> The simulator for conversations.

**[conversationsimulator.com](https://conversationsimulator.com)** &nbsp;·&nbsp;
**[Documentation](https://docs.conversationsimulator.com)** &nbsp;·&nbsp;
**[Download](https://conversationsimulator.com/download/)**

Practice interviews, negotiations, language, and difficult social situations with AI
NPCs — running **100% on your computer**, no account, no cloud, no telemetry.

![One turn of "Making the Case" in Conversation Simulator, played back at 6x with that factor and the turn's real length, 111 seconds, labelled along the bottom: the player types a reply into the composer, the panel under the transcript reads "Elena Vasquez is thinking…" with a reading bar and "Reply starts in about 9–15 s", the NPC's reply arrives a sentence at a time, the transcript reads "Updating the scene…", and the Conversation meters above the transcript move as the turn lands — Trust up 10 to 95 and Openness up 5 to 70.](docs/assets/demo.gif)
<!-- Captured from a real session on a local Qwen3 4B model. Capture environment and the
     command that remakes every asset here: docs/screenshots.md -->

```
Scenario: Making the Case  ·  Job Interview Basics pack
You:   "I read your last three release notes and spoke to two of your logistics customers.
        What surprised me is that the retention story is not the dashboard — it is the CSV
        export people build their Monday reports on. …"
NPC:   "That's insightful. You've done your homework and understood the nuances of our
        product. Let me ask — how do you see this impacting your approach to planning
        and execution? …"
Flags:  player_demonstrates_knowledge
State:  trust 95  ·  openness 80  ·  conviction 35  ·  preparation_score 55
```

---

## Why this exists

Every AI conversation coach on the market — interview prep, sales roleplay, speaking
coaches, VR soft-skills training — runs in the cloud. But the conversations people most
need to rehearse (firing someone, the salary ask, the breakup, the visa interview) are
exactly the ones they least want on somebody else's server. Conversation Simulator is the
missing intersection: a **structured practice game** (live scenario state, events, scoring,
debrief) with **100% local inference** (no account, no cloud, no telemetry), in the
**open** (Apache-2.0) — heir to a sixty-year lineage that runs from ELIZA through Monkey
Island's insult sword-fighting to Façade, finally buildable because local LLMs dissolved
the authoring wall those earlier systems hit.

> The full analysis — lineage, competitive field, and the business-model precedents from
> Dwarf Fortress to Shattered Pixel Dungeon: **[docs/landscape.md](docs/landscape.md)**

---

## Screenshots

| Screen | What you see |
|--------|-------------|
| [![Conversation Simulator home screen. Links run down the page — Start a scenario, Create / edit a scenario, Install model, Import pack, Creator workbench guide, Read docs — above a "Your training" card showing two sessions, a one-day streak and a link to the full logbook, and a three-scenario training plan: At the Convenience Store, Checking In at Hôtel Lumière and Coffee at Café Sol. The Status panel reports AI engine: Ready, AI model: qwen3-4b-instruct-q4_k_m.gguf, Voice input and Voice output: Not installed, Network required to play: No, and Packs: 6 installed.](docs/assets/screenshots/01-home.png)](docs/assets/screenshots/01-home.png) | **Home** — what is running, and that none of it needs the network |
| [![Scenario Library filtered by the search word "interview": four scenarios in one pack. Rating, language, difficulty and tag filters and a Voice only checkbox sit beside the search box. The Job Interview Basics pack, with Open folder and Validate pack buttons, lists Making the Case, The Behavioral Interview, The Executive Gauntlet and The Foreman's Interview. Each card carries a summary, chips for content rating, player role, length, language, difficulty and tags, and a Launch button.](docs/assets/screenshots/02-scenario-library.png)](docs/assets/screenshots/02-scenario-library.png) | **Scenario Library** — search and filter installed packs |
| [![The conversation screen mid-session in "Making the Case". Elena Vasquez's card reads Mood: Impressed and Listening beside a scene card describing the stretch-hire interview, under a "Something changed: Gap probing" banner. The Conversation meters panel above the transcript reads Trust 85 (up 15 this turn), Patience 85 (up 10), Rapport 70 (up 20), Openness 65, Objective progress 0, Conviction 35 and Preparation score 45. The transcript numbers whole turns — Turn 2 · You, Turn 2 · Elena Vasquez, Turn 3 — with the player's lines in violet, the NPC's replies in green and a Mood line under each reply, above the text composer.](docs/assets/screenshots/03-conversation.png)](docs/assets/screenshots/03-conversation.png) | **Conversation** — the reply as it is written, and meters that move each turn |
| [![Session Debrief scoring the session 52 out of 100 with a "Player Exit" outcome badge and four turns. A written summary is followed by a five-row scorecard — Experience Gap 53, Learning Velocity 53, Self-Awareness 52, Transferable Skills 51 and a second Self Awareness row at 52 — then a Telemetry panel showing talk ratio, words per turn, question counts, a median response latency of 99 seconds on the capture machine, and a sparkline for each conversation meter across the four turns. Strengths are listed in green, each quoting the turn it came from, and areas for improvement in amber.](docs/assets/screenshots/04-debrief.png)](docs/assets/screenshots/04-debrief.png) | **Debrief** — score, rubric scorecard, what to fix |
| [![Creator Workbench. A green "Pack is valid" banner sits above a two-column layout. On the left, the pack list — six official packs and an editable local-dev copy of Job Interview Basics — sits above that copy's file tree, with scenarios/stretch_role_interview.yaml selected. On the right, Edit and Test Chat tabs sit over a YAML editor showing the file — schema_version, scenario_id, title, summary, player_role, and the npc, scene and rubric references — with YAML and Form editor toggles, a Save button and an Export .zip button.](docs/assets/screenshots/05-creator-workbench.png)](docs/assets/screenshots/05-creator-workbench.png) | **Creator Workbench** — edit packs in YAML, validate as you go |
| [![Model Manager. "Set up your model" offers three cards: install the recommended Qwen3 4B Instruct Q4_K_M (2.5 GB, Apache-2.0, requires 4 GB VRAM, tagged Fast with an expected 0.8 to 2.4 second time to first token on the recommended tier), use a model already installed in local Ollama, or point the app at a GGUF file already on the machine.](docs/assets/screenshots/06-model-manager.png)](docs/assets/screenshots/06-model-manager.png) | **Model Manager** — install one, or bring your own |

> Real captures from one playthrough on a local Qwen3 4B model, on a four-core machine with
> no graphics card — so the recording above is played at 6x and says so, and the voice
> runtimes are left uninstalled.
> [docs/screenshots.md](docs/screenshots.md) records the capture environment, the alt
> text for every image, and the one command that remakes them.

---

## Quickstart

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh     # check env, install packages, create ~/.convsim/
./scripts/dev.sh       # start all services
```

Then open **http://127.0.0.1:7354** in your browser.

**Windows:** use `scripts\setup.ps1` and `scripts\dev.ps1` instead.

On first launch you will be prompted to download a local model. The recommended
starter is **Qwen3 4B Instruct Q4\_K\_M** (~2.5 GB, Apache-2.0). No model is
bundled — you decide what to install and when.

> Full install guide: [docs/install.md](docs/install.md) &nbsp;·&nbsp;
> Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)

---

## Your first scenario

1. Complete the quickstart above.
2. In the browser, pick **Job Interview Basics → The Executive Gauntlet**.
3. Read the player brief, then start typing.
4. When the conversation ends, open the debrief — scores, turning points, and
   coaching notes are all generated locally.
5. Adjust difficulty or edit the scenario YAML and run it again.

---

## Starter scenario packs

| Pack | Scenarios |
| ---- | --------- |
| **Job Interview Basics** | Behavioral, hostile executive, blue-collar trade, stretch role |
| **Everyday Negotiation** | Used car, apartment lease, freelance scope, customer service refund |
| **Language Café** | Spanish coffee shop, French hotel check-in, Japanese convenience store, English small talk |
| **Difficult Conversations** | Coworker feedback, missed-deadline apology, boundary with a friend, ask for a raise |
| **Dating — Confidence & Boundaries** | Asking someone out, accepting a no, turning down a neighbor, a first date |

**First Words**, a scripted tutorial of 3 to 5 minutes, ships alongside them
and needs no model download. The app imports every pack in `packs/official/`
when it starts.

The scenario packs are CC BY 4.0 and the First Words tutorial is Apache-2.0.
Fork them, remix them, or create your own from scratch.

---

## Building a scenario pack

A pack is a folder of YAML files — no code, no build step, no compilation.

```
packs/
  my-pack/
    manifest.yaml          # pack id, title, author, content rating
    scenarios/
      my_scenario.yaml     # opening line, goals, state variables, events
    npcs/
      my_npc.yaml          # persona, tone, backstory, goals
    rubrics/
      my_rubric.yaml       # scoring dimensions and weights for the debrief
    safety/
      my_policy.yaml       # content categories and per-category actions
    scenes/
      my_scene.yaml        # visual and atmospheric context
```

The fastest way to build a pack is the **Creator Workbench** (in the app
navigation). Copy an official pack, edit the YAML files, validate with one
click, quick-test in the browser, and export a shareable `.zip` — all
without leaving the browser.

**New to pack authoring?** `packs/sample/hello-conversation/` is a
minimal one-scenario sample pack (CC0-1.0, public domain) with every
required file type and inline comments explaining each field. Copy it into
`packs/local-dev/` and start editing — or import its zip in the Creator
Workbench.

Minimal `scenarios/my_scenario.yaml`:

```yaml
schema_version: "0.1"
scenario_id: my_scenario
title: My First Scenario
summary: A one-line description of the situation the player faces.
player_role:
  label: Your Role
  brief: What the player is trying to accomplish in this conversation.
npc:
  ref: ../npcs/my_npc.yaml
rubric:
  ref: ../rubrics/my_rubric.yaml
duration:
  max_turns: 12
opening:
  npc_says: "Let's begin."
goals:
  player_visible:
    - "Reach a clear agreement without giving up your core need"
state:
  variables:
    rapport:
      min: 0
      max: 100
      default: 50
      visibility: visible
      max_delta_per_turn: 15
```

Add events, endings, difficulty modifiers, and extra rubric dimensions as you go.
The JSON Schema in `schemas/` validates everything at import time.

> Sample pack: [packs/sample/hello-conversation/](packs/sample/hello-conversation/) &nbsp;·&nbsp;
> Creator workbench tutorial: [docs/scenario-authoring.md](docs/scenario-authoring.md) &nbsp;·&nbsp;
> Pack validation: [docs/pack-validation.md](docs/pack-validation.md) &nbsp;·&nbsp;
> Official quality bar: [docs/official-pack-quality-bar.md](docs/official-pack-quality-bar.md)

---

## Local-first promise

> Conversation Simulator does not send your conversations, audio, prompts,
> transcripts, or model outputs to any server during play.

| What | Where it runs |
| ---- | ------------- |
| LLM inference | Local model via llama.cpp — stays on your machine |
| Speech-to-text | whisper.cpp — local, no audio uploads |
| Text-to-speech | Kokoro, a local server; TTS audio cached on disk |
| Transcripts | SQLite in the `db/` folder of the app's [data folder](docs/install.md#data-locations), never uploaded |
| Telemetry | None — `telemetry_enabled` defaults off and the MVP ships no telemetry subsystem |
| Model downloads | Only when you explicitly request them; license shown before every download |

All services bind to `127.0.0.1`. Nothing is reachable from other machines by default.

Verify the offline guarantee at any time:

```bash
npx convsim offline-smoke-test packs/official/job-interview-basic
```

The command runs a scripted conversation with a fake runtime and confirms no
outbound TCP connection was made. It exits nonzero with an actionable error if
any subsystem attempts to reach an external host.

> Full data policy: [docs/privacy.md](docs/privacy.md) &nbsp;·&nbsp;
> Network security: [docs/network-security.md](docs/network-security.md)

---

## Architecture

Everything runs on your machine and, by default, listens only on localhost.
The browser never talks to the internet.

```
┌──────────────────────────────────────────────────────────────┐
│                        Your machine                          │
│                                                              │
│  Web UI (React)                                              │
│  :7354 Vite dev server in a source build;                    │
│  the desktop app shows it in its own window                  │
│       │  HTTP REST + WebSocket (localhost only)              │
│       ▼                                                      │
│  convsim-core  :7355  (Python / FastAPI)                     │
│       │                   SQLite  <data folder>/db/          │
│   ┌───┼──────────────┐                                       │
│   ▼   ▼              ▼                                       │
│  :7356  no port      :7358                                   │
│  LLM    STT          TTS                                     │
│  llama  whisper-cli  Kokoro                                  │
└──────────────────────────────────────────────────────────────┘
```

| Component | Port | Responsibility |
| --------- | ---- | -------------- |
| Web UI | 7354 | Browser UI. The Vite dev server serves it in a source build; the desktop app loads it into its own window and opens no port for it |
| convsim-core | 7355 | Scenario engine, REST API, WebSocket |
| llama-server | 7356 | Local LLM, a process convsim-core starts |
| whisper-cli | none | Speech-to-text (whisper.cpp), which convsim-core runs as a subprocess for each request |
| Kokoro server | 7358 | Text-to-speech. convsim-core connects to a Kokoro server on this port when one is running; the app does not ship or start one |

> Architecture deep-dive: [docs/architecture.md](docs/architecture.md) &nbsp;·&nbsp;
> Runtime adapters: [docs/runtime-adapters.md](docs/runtime-adapters.md)

---

## Model requirements

No model is bundled. The app shows license information and size before each download.

| Model | Size | VRAM | License | Role |
| ----- | ---- | ---- | ------- | ---- |
| Qwen3 4B Instruct Q4\_K\_M | 2.5 GB | 4 GB+ | Apache-2.0 | Starter (lower-spec machines) |
| Qwen3 8B Instruct Q4\_K\_M | 5.0 GB | 6 GB+ | Apache-2.0 | Standard (recommended for most) |
| Qwen3 14B Instruct Q4\_K\_M | 9.0 GB | 10 GB+ | Apache-2.0 | High quality |
| Mistral Small 3.1 24B Q4\_K\_M | 14.3 GB | 16 GB+ | Apache-2.0 | High quality, long context |

You can also load any llama.cpp-compatible GGUF file from your own filesystem.
The full model registry with checksums is in `model-registry/registry.yaml`.

> Local models guide: [docs/local-models.md](docs/local-models.md)

---

## Safety

Every session runs through a layered safety system before and after the model is called.

- Two categories are **global and cannot be disabled by any pack**: content
  involving minors in a romantic or sexual context always stops the session;
  self-harm crisis language always stops the session and surfaces real crisis resources.
- Input is checked deterministically before the NPC runtime is invoked.
- Packs are **declarative YAML only** — no executable code. The validator blocks
  scripts, binary files, symlink attacks, and prompt-injection patterns at import time.
- Community packs can tighten safety rules for their scenario; they cannot weaken
  the global non-overridable rules.
- Content cap: the platform supports G, PG, and PG-13 ratings. Nothing above PG-13
  is permitted in any pack.

> Full safety policy: [docs/safety-policy.md](docs/safety-policy.md)

---

## Roadmap

| Milestone | Goal | Status |
| --------- | ---- | ------ |
| 0 | Monorepo skeleton, dev setup, official scenario packs | Complete |
| 1 | Text-only local simulator (browser UI + Python backend + local LLM) | Complete |
| 2 | Scenario pack system (import, validate, browse community packs) | Import, export and validation complete; in-app community pack browser planned ([#465](https://github.com/outrightmental/ConversationSimulator/issues/465)) |
| 3 | Local voice input (Whisper speech-to-text) | Complete (opt-in) |
| 4 | Local voice output (TTS with Kokoro / sherpa-onnx) | Complete (opt-in) |
| 5 | Polished playable alpha | Complete (v0.1.0-alpha.1); v0.4.0 is the first public demo |

**[ROADMAP.md](ROADMAP.md)** — MVP acceptance criteria, build order, what is
deliberately out of scope, and links to the acceptance criteria and docs.

> [Delivery board](https://github.com/orgs/outrightmental/projects/12) — every issue ever shipped, in phases &nbsp;·&nbsp;
> [GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones) &nbsp;·&nbsp;
> [Full specification](docs/SPEC.md) &nbsp;·&nbsp;
> [Post-alpha issues](docs/post-alpha-issues.md)

### How it's distributed

Conversation Simulator is **free and open source, and fairly priced**:

- **GitHub — free.** Clone this repository, build it with the quickstart above,
  and run it at no cost. The engine and the First Words tutorial are Apache-2.0,
  and the official scenario packs are CC BY 4.0.
- **Steam — $9.99.** The [Steam edition](publishing/STEAM_STORE_PAGE.md) is the
  same software, packaged: signed, notarized, auto-updating.
  The price funds continued development; it does not unlock anything the source
  build lacks. The Steam edition makes the same local-first guarantee as the
  open-source build.
- **Steam demo — free.** A [demo edition](docs/steam-next-fest-demo.md) of the
  Steam build — one model download, five curated conversations, nothing else —
  ships as a separate free Steam app for Steam Next Fest. Everything you practise
  in it carries over to the full game.
- **Premium scenario-pack DLC — Steam only.** First-party expansion packs beyond
  the free official ones are developed in a separate **private** repository
  and sold as paid Steam DLC. Their content is never in this public repository.
  See [docs/DLC_MODEL.md](docs/DLC_MODEL.md) for the private-repo → Steam-DLC
  contract. The open core never shrinks: nothing that ships free is relocked as DLC.

This free-on-GitHub, fairly-priced-on-Steam pattern has a strong track record — Dwarf
Fortress, Shattered Pixel Dungeon, Mindustry, Aseprite — and the reasoning behind it is
laid out in [docs/landscape.md](docs/landscape.md#business-model-precedents).

The Steam release documents:

| Document | Purpose |
|----------|---------|
| [docs/STEAM_ROADMAP.md](docs/STEAM_ROADMAP.md) | Release principles and release train (Stages 1–5) |
| [publishing/STEAM_STORE_AND_OPERATIONS.md](publishing/STEAM_STORE_AND_OPERATIONS.md) | Store page operations, launch runbook, support triage |
| [publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md](publishing/STEAM_PUBLISHING_AND_DEPLOYMENT.md) | SteamPipe concepts, CI deploy, manual upload, branch promotion, troubleshooting |
| [docs/STEAM_INTEGRATION.md](docs/STEAM_INTEGRATION.md) | Steam API bridge, Steam Cloud exclusions, achievements, stats, rich presence |
| [publishing/MACOS_SIGNING_AND_NOTARIZATION.md](publishing/MACOS_SIGNING_AND_NOTARIZATION.md) | macOS Apple Developer ID signing and notarisation |
| [publishing/WINDOWS_CODE_SIGNING.md](publishing/WINDOWS_CODE_SIGNING.md) | Windows Authenticode signing |

---

## Beta testing

Running a pre-release build?  Use **Support → Report a problem** in the app to
assemble a redacted diagnostics bundle and open a pre-filled GitHub issue — all
in under a minute, nothing uploaded automatically.

> [docs/beta-testing.md](docs/beta-testing.md) — how to join, where to report,
> what a good report looks like

---

## Contributing

All contributions are welcome — new scenario packs, bug fixes, documentation
improvements, or new runtime adapters. Scenario packs are the friendliest entry point —
you can ship one without touching engine code.

**Start here:**
[`good first issue`](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+state%3Aopen+label%3A%22good+first+issue%22) &nbsp;·&nbsp;
[`help wanted`](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+state%3Aopen+label%3A%22help+wanted%22) &nbsp;·&nbsp;
[Delivery board](https://github.com/orgs/outrightmental/projects/12) &nbsp;·&nbsp;
[How the project is run](docs/governance.md)

> [CONTRIBUTING.md](CONTRIBUTING.md) &nbsp;·&nbsp;
> [CODE\_OF\_CONDUCT.md](CODE_OF_CONDUCT.md) &nbsp;·&nbsp;
> [SECURITY.md](SECURITY.md) &nbsp;·&nbsp;
> [RELEASE\_NOTES.md](RELEASE_NOTES.md)

---

## Repository layout

```
apps/
  web/             React / TypeScript browser UI
  desktop/         Tauri desktop wrapper (the packaged and Steam builds)

packages/
  ui/              Shared UI component library
  scenario-schema/ TypeScript types for scenario packs
  shared-types/    Shared TypeScript types across apps and services

services/
  convsim-core/    Python / FastAPI — scenario engine, REST API, WebSocket

runtimes/
  llama_cpp/       llama.cpp integration and binary management
  whisper_cpp/     whisper.cpp speech-to-text integration

packs/
  official/        First-party packs: the scenario packs listed above (CC BY 4.0)
                   and the First Words tutorial (Apache-2.0)
  sample/          hello-conversation, a minimal sample pack (CC0-1.0)

schemas/           JSON Schema definitions for packs, scenarios, NPCs, rubrics
model-registry/    Curated registry of supported local models with checksums
docs/              Documentation (CC BY 4.0)
scripts/           Developer setup and launch scripts
```

---

## Licensing

| Content | License |
| ------- | ------- |
| Application code | Apache-2.0 |
| Official scenario packs | CC BY 4.0 |
| First Words tutorial pack | Apache-2.0 |
| Documentation | CC BY 4.0 |
| Captured screenshots and demo recording, placeholder pack art | CC0-1.0 |
| Model weights | Not bundled — user-installed with full license disclosure |
| Premium scenario-pack DLC | Proprietary — not in this repository; sold on Steam |

Everything in **this** repository is open source: the code and the First Words
tutorial are Apache-2.0, and the official scenario packs and the docs are
CC BY 4.0. The paid Steam build is a packaging of this same open code — buying
it funds development, not access. Premium expansion
packs are the only proprietary content; they live in a separate private repository
and are never included here.

`LICENSE` contains the full Apache-2.0 text.  
`NOTICE` lists copyright notices and per-artifact license details.
