<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Conversation Simulator v0.4.0 — Release Notes

> **Minor release (2026-11-10).** This is the release the free demo edition
> is built from. The character's reply reaches the screen a sentence at a time
> while the model writes it. The wait says what the turn is doing and, once
> turns have been measured on this machine, when the reply will start. The
> first session explains itself, the Conversation Brief leads with the
> mission, and the engine launches sized for one conversation. This is the
> first tag since v0.2.9, so everything merged since then ships here. The
> v0.3.0 notes further down were written in July and never tagged; that work
> reached players through the v0.2.x patch releases.

## What's new in v0.4.0

### The reply arrives as it is written (#538)

The NPC's words used to land all at once, after the whole turn had been
generated and checked. They now reach the screen a sentence at a time while
the model is still writing, over a WebSocket at `/ws/session/{id}` that
convsim-core serves itself.

- A sentence is released only after the output check has passed on everything
  released so far, and released text is committed text. If a later sentence
  fails the check, it is withheld, generation stops, and the turn is committed
  with the sentences already shown and no state change. If the reply is cut
  off, the turn keeps the released line and every part of the model's output
  that closed before the cut, with defaults for the rest. Either way the turn
  is marked `salvaged`, no second model call is made, and nothing the player
  has read is taken back. The repair and retry path runs only when nothing was
  released.
- One turn runs at a time per session. A second submission while a turn is
  running answers `409 TURN_IN_PROGRESS`. A message typed after the whole line
  is on screen, while the turn is still being saved, is queued and sent when
  the turn commits.
- The socket accepts the desktop webview's origins and the Vite dev server's
  (port 7354), and answers any other browser origin with a 403. Events are not
  stored or replayed: a client that reconnects is sent the session's current
  state, and the transcript stays the record.

### The wait says what it is doing (#539, #519)

In v0.2.9 the wait was "NPC is responding…", a notice after five seconds
that the NPC was taking longer than usual, and a performance banner. The
panel under the transcript now says which stage the turn is in, with the
character's name where the pack gives one: getting ready, thinking (reading
the prompt), replying, updating the scene, trying again (a repair or safety
retry) and getting the voice ready.

- While the engine reads the prompt, a bar fills from the engine's own
  progress reports, with the part it already had cached drawn in. llama-server
  sends them; Ollama does not, so its bar shows no fraction.
- "Reply starts in about 5–8 s." appears only while the turn is getting ready
  or reading, and only when the reply is four seconds or more away. It is
  worked out from this machine's measured speeds (the medians over its newest
  twenty recorded turns on the same engine and model) and how much of the
  prompt is left to read; before the engine's first progress report it is the
  measured time to first words less the time already waited. It counts down
  with the clock, and each end of the range is rounded to whole seconds under
  ten seconds, to five seconds under a minute, and to whole minutes from a
  minute on.
- From five seconds the panel adds one footnote: the next replies can be
  shortened under Reply speed, in Settings. It is text, not a link, because
  leaving the screen mid-turn would lose the pending message. The demo adds
  that closing other apps usually helps.
- Each stage is announced once to assistive technology, "Your turn." is
  announced when the reply lands, and focus rests on the panel while the turn
  runs. A reduced-motion preference stops the bar's fill animation.
- The performance warning banner, which told players to raise GPU layers, and
  the slow notice are gone. A timed-out turn now suggests Quick replies (and,
  in the full app, a smaller model) instead.
- Every NPC turn now records what it cost: prompt tokens read and reused from
  cache, output tokens, reading and writing speed, the time at each stage
  boundary, extra model calls (repair, safety retry) with their own time,
  voice synthesis time, and the model that served it, never as a file path.
  llama-server supplies its timings and prompt progress, Ollama the figures in
  its final chunk, and the built-in fake runtimes fixed values. The record
  rides on the turn response, the transcript and the session's debug view, and
  `GET /api/performance/rolling` reports this machine's medians over the
  newest twenty records for one engine and model, leaving out stopped and
  fallback turns. It is stored with the session, deleted with it, included in
  a session export, and sent nowhere (`docs/privacy.md`).

### The engine launches for one conversation (#523)

llama-server used to start with its own defaults, which suit a shared
inference server: four slots, the model's full trained context, an 8 GiB
prompt cache and a 2048-token batch. The app now starts it with one slot, a
context size from the model registry (8192 tokens for the three Qwen3
entries, 32768 for Mistral Small 3.1 24B; a GGUF file you register yourself
gets the context you stated, or 8192), a 256-token batch and a prompt cache
bounded at 1 GiB. With one slot the conversation has the whole context rather
than a share of it, prompt progress arrives every batch rather than once per
prompt, and the cache cannot grow past its bound. The context size goes on
the command line; the other three travel as `LLAMA_ARG_*` environment
defaults, which an older engine ignores. A value already set in the
environment wins for all four, and `runtime.log` records what the engine was
started with.

### The first session explains itself (#501)

Playtest feedback said the first few sessions felt "both too sparse and too
technical". Four things changed.

- **Resume.** `GET /api/sessions` lists a profile's sessions. An unfinished
  conversation can be picked up from a *Conversation in progress.* strip in
  the app's frame, a *Resume your conversation* action on Home, or the
  *Resume* button that *Your sessions* in Settings shows beside each
  conversation still in progress. A reload or relaunch resumes it too.
- **Reply speed.** One setting in Settings (*Quick replies*, *Balanced*,
  *Fuller replies*) scales how many words the character writes per turn, the
  dominant cost of a turn on local hardware. It takes effect on the next
  message, with nothing to restart.
- **Plain wording.** The welcome screen asks how familiar the player is with
  AI language models, and the answer picks plain or technical wording (the
  *Wording* setting in Settings). Plain wording hides session ids, internal
  state names and event flags. At either level the character is called by
  name wherever the pack gives one. The tutorial no longer says "scenario
  event", "hidden prompt" or "rubric dimensions", and it answers questions
  about the meters, its mood, whether it is an AI, how conversations end and
  what the debrief is, instead of carrying on with the next scripted line.
  The First Words debrief asks about wording once more.
- **Meters and turns.** The two meters sit above the transcript in a labelled
  *Conversation meters* panel, show how far they moved this turn, and are kept
  apart from the character's *Mood*. A turn is the player's message plus the
  reply, so the transcript and the debrief count the same thing.

### The Conversation Brief leads with the mission (#500)

The pre-conversation screen read as a wall of identical form controls. It is
now in three tiers. First the mission: pack, title, situation and the
scenario's player-visible goals, numbered under *Your objective* in the one
lit panel. Then the two decisions that change the conversation, *Difficulty*
and *Your role*. The five mechanical settings (input, audio, language,
privacy and the variation seed) are grouped in one dimmer *Session setup*
card, each still one Tab or D-pad press away. The launch bar with *Start
conversation* stays pinned to the bottom of the screen. Scenario details from
the API now carry `player_visible_goals`; the hidden goals never leave the
server. A difficulty level with no description shows its name once instead of
twice.

### The demo has its own icon (#499)

The Steam demo and the full app showed the same icon in the Steam client. The
demo edition now bundles its own icon set: the same speech-bubble mark on a
deep purple plate instead of the full app's teal, with a "DEMO" ribbon at
128 px and above. `publishing/assets/source/gen_icons.py` generates that set
and the Steamworks App Icon and Shortcut Icon from one source, the bundle's
`icon.icns` serves as the Mac Icon, and 39 acceptance cases check the result.

### Copy diagnostics works on macOS, and a rejected request says why (#508)

The web clipboard APIs are unusable in the packaged macOS and Linux webviews,
so *Copy diagnostics* dead-ended at "Copy failed". Every copy button now
writes through the desktop shell's clipboard first, then the browser
clipboard API, then the older copy command. A request that convsim-core
rejects (`422`) names the field and the rule it broke instead of "Request
validation failed", is written to the log the diagnostics report collects,
and never echoes the rejected value. An explicit `null` for an optional
setting means "use the default".

### Model downloads show the real folder and offer Retry (#568)

The confirm-install screen's *Saves to* row (*Storage path* in the model
manager) showed `~/.convsim/models/llm/<id>.gguf`, a folder the engine no
longer writes to. It now reads the Models folder from
`GET /api/privacy/folders`, the same source Settings uses, and shows
`<folder>/<id>.gguf`, or a *File name* row with `<id>.gguf` alone while the
folder loads or if the request fails. On the installing screen, Retry used to
depend on matching the error text, which the download library's messages
never matched, so a player whose connection dropped saw an opaque error.
Every download failure is now classified as `NETWORK`, `HTTP`, `CHECKSUM` or
`UNKNOWN` with a message that is never empty, the code is stored with the
install and returned by the install status API, and a `NETWORK` failure shows
*Network connection lost* with *Retry*.

### Also since v0.2.9

- Slow turns are no longer failed at 60 seconds (#489). The conversation
  screen waits up to five minutes and checks the saved transcript before
  giving up, so a reply the server already has is shown rather than rolled
  back. A stalled engine answers `504 TURN_TIMEOUT` and an unreachable one
  `503 RUNTIME_UNAVAILABLE`.
- The Conversation Brief first became a briefing in #486: styled cards in
  place of unstyled fieldsets, difficulty rows that draw the character's
  traits as meters, and a launch bar pinned to the bottom of the screen. The
  mission-first layout above builds on it.
- convsim-core runs as a supervised desktop sidecar (#456, #485). Readiness is
  a `GET /api/health` exchange rather than an open port, a core that exits on
  its own is restarted up to three times with backoff, and quitting shuts down
  the whole process tree, including llama-server and the voice sidecar.
- A per-model clock, the median of this machine's recent whole turns, showed
  how long a turn would take while the model was thinking (#488). The staged
  panel above replaces it whenever the core reports stages, and falls back to
  it when no socket delivers them.
- The README and docs carry six screenshots and a demo recording captured from
  a real local-model session (#455). They predate the v0.4 conversation
  screen; see Known gaps.
- Diagnostics and the crash and beta reports name the release version instead
  of the package version, which always read 0.1.0 (#490, #498).
- The issue tracker's labels, fields and milestones are declared in
  `.github/project-structure.yml` and validated in CI (#491).
- CI fixes: the UI package declares the TypeScript it type-checks with
  (#558), the `stop_all` concurrency test waits on a rendezvous instead of a
  stopwatch (#561), and the launch tests fail if a launch setting is dropped
  or moved onto the command line (#567).

## Upgrade notes

- One database migration, `0019_install_error_code`, runs when convsim-core
  starts. It adds a nullable `error_code` column to `installed_models` and
  `setup_install_jobs`. Rows written before it keep no code, and the
  installing screen falls back to the old text match for them.
- Turn timing records need no migration: they are stored as `turn_timing`
  events in the existing session events table.
- Two new settings, *Reply speed* and *Wording*, start at *Balanced* and plain
  wording. A player who set up before this release does not see the welcome
  screen's familiarity question; the next First Words debrief asks about
  wording once, and both settings can be changed in Settings at any time.
- The session WebSocket is served by convsim-core on its API port, 7355, so
  streaming needs nothing else running.
- For developers: the root `package.json` `engines` field now asks for
  Node.js 20 or newer (it said 18). Use Node 22 or 24; CI runs 24. The locked
  better-sqlite3 12.11.1 declares Node 20.x and 22.x through 26.x, and
  publishes prebuilt binaries only for Node 22, 24, 25 and 26. On Node 20, 21
  or 23, `pnpm install` finds no prebuilt binary and compiles better-sqlite3
  from source with node-gyp, which needs Python and a C++ build toolchain;
  without them the install fails. On Node 18 or 19, pnpm warns
  `Unsupported engine`, carries on, and then compiles it the same way. The
  setup scripts and the first-run check still accept Node 18, so passing them
  does not mean the install will succeed.

## Known gaps

- The screenshots and the README's demo recording show the pre-v0.4
  conversation screen, with the old performance advisory and the meters below
  the transcript. Recapturing them needs a real local-model session (#554).
- The macOS build is Apple Silicon only (the release workflow builds
  `macOS-aarch64` alone), while the Steam store copy's macOS requirements list
  Intel processors too (#563).
- Model names are shown as the registry writes them, for example "Qwen3 4B
  Instruct Q4_K_M" (#555).
- The reply-start estimate needs turns measured on this machine with the same
  engine and model before it can appear. The first turn on a fresh machine, or
  on a newly chosen model, shows the stages and the clock without one.
- The First Words tutorial is defined twice, as a pack and as a catalog entry.
  Tests hold both copies to the same wording rules until they are merged
  (#553).
- Valve has not granted the Steam Deck Verified tier. The QA matrix lists it
  as an open gate (G4-02) for the public release.
- With more than one model in Ollama, conversations and debriefs use the
  first model `ollama list` shows. The model chosen with *Use this model* is
  used only by the benchmark, and is the name Home shows.
- Choosing another llama.cpp model while the engine is running saves the
  choice, but the engine keeps the old model until the app is quit and
  reopened.

---

# Conversation Simulator v0.2.8 — Release Notes

> **Patch release (2026-09-16)** — Steam overlay on Windows, and the
> Steamworks SDK finally in the Steam build. Responds to Valve's build review
> of BuildID 24431329 (v0.2.6): "The Steam Overlay doesn't appear when
> pressing Shift+Tab."

## What's fixed in v0.2.8

### The Steam overlay works on Windows (Shift+Tab and F12)

Three things had to be true for the overlay to appear, and none of them were:

1. **The Steamworks SDK was never in the shipped build.** Every Steam depot up
   to v0.2.7 was compiled without `--features steam`, so `SteamAPI_Init` never
   ran — achievements, stats, rich presence, Workshop, DLC checks and the
   Shift+Tab forwarder added in v0.2.7 were all inert. The Windows Steam build
   now enables the feature and ships Valve's signed `steam_api64.dll`.
2. **Shift+Tab never reached Steam.** The chord lands in the WebView2 process,
   which Steam's input hook cannot see. The app forwards Shift+Tab (and now
   F12) to Steam itself.
3. **Steam had nothing to draw into.** Steam renders the overlay by hooking the
   game's swapchain, and a WebView2 app has none. The app now hosts a
   transparent, click-through compositing surface (vendored
   `tauri-plugin-steam-overlay-surface`, MIT) that Steam composites the overlay,
   toasts and notifications into.

Also new: a Steamworks callback pump (no Steam callback could fire before),
hooked F12 screenshots that capture the live app instead of a black frame, and
a `steam_overlay_status` diagnostic for QA.

**Scope:** Windows only. The macOS and Linux Steam builds still ship without
the SDK (their packaging does not yet bundle `libsteam_api`), and
overlay-over-WebKit remains open — see
[`docs/STEAM_INTEGRATION.md`](docs/STEAM_INTEGRATION.md#platform-scope).

### Compliance

Assessment of the PRC *Interim Measures for the Administration of AI
Anthropomorphic Interaction Services* (in force 2026-07-15) added at
[`publishing/PRC_AI_ANTHROPOMORPHIC_INTERACTION_MEASURES.md`](publishing/PRC_AI_ANTHROPOMORPHIC_INTERACTION_MEASURES.md)
and tracked as risk SP-07.

### Build and CI

- `steamworks` 0.11 → 0.13 (thread-safe client, screenshots API); MSRV 1.80.
- New CI job compiles the shipped configuration (`cargo check --features steam`
  on Windows) on every PR; `scripts/desktop-smoke.sh` also checks the feature.

---

# Conversation Simulator v0.3.0 — Release Notes

> **Minor release** — onboarding overhaul. A new user reaches their first
> conversation in under 60 seconds on every supported platform, with zero error
> screens on the happy path.

---

## What's new in v0.3.0

### Onboarding overhaul — first conversation in 60 seconds (Epic #388)

v0.2.2 greeted new users with a "System Check" wall of infrastructure failures
(`llama-server binary not found`). Fix buttons either opened docs describing UI
that didn't exist or dead-looped back to the Welcome screen. On Windows the
engine wasn't provisionable natively at all.

v0.3.0 replaces that experience end-to-end.

#### Welcome: one decision, two cards (#381)

The new Welcome screen presents a single choice between two clearly labelled
cards:

- **"Set me up ⭐"** — one click starts the full install pipeline (engine →
  model → verify → warmup → packs). The AI model arrives in the background while
  you play.
- **"Try it right now"** — launches the scripted "First Words" tutorial
  immediately, with no download required, in under 15 seconds.

Ollama and local GGUF paths are demoted to a collapsible **Advanced** disclosure
with an explanation of when and why you'd use them. The privacy promise appears
as a calm one-liner in the Advanced section, not as a gate.

#### Play while it downloads (#383)

The scripted tutorial (`first-words` pack) runs with the built-in fake runtime —
no model required. A persistent header pill shows download progress. When the
real model is ready, a toast offers an immediate switch. The happy path is
playable before any download completes.

#### One-click background install pipeline (#382, #379)

`POST /api/setup/install` starts a resumable pipeline: engine provisioning →
model download (with SHA-256 checksum) → verify → warmup → pack registration.
Progress is streamed via `GET /api/setup/install/{id}`. If the app is closed
mid-download and relaunched, `pending_setup_job_id` in the status response
re-attaches the UI to the running job automatically.

Windows now provisions the inference engine natively — no WSL2 required.

#### Self-healing checks and remediation cards (#384)

The old "System Check" wall is gone. Auto-fixable failures are resolved silently.
Only decisions that genuinely require the user (insufficient disk, offline,
platform choice) surface as remediation cards in plain language with a single
action and a text-only escape hatch. The forbidden-vocabulary invariant ensures
no card ever shows internal terms (`binary`, `sidecar`, `llama`, `preflight`,
`gguf`).

#### Dead-loop fixed (#378)

In v0.2.2 every fix button on the System Check screen redirected back to Welcome
because `FirstRunGuard` treated `/model-manager` as an unauthenticated route and
rewrote it to `/first-run`. Every `fix_action.href` is now verified in CI to
never point at `welcome` or `/first-run`.

#### Server-authoritative setup state (#380)

`GET /api/setup/status` is the single source of truth — `{ kind: "never-run" |
"incomplete" | "ready", pending_setup_job_id, onboarding_outcome }`. The browser
keeps a localStorage fast-path mirror but always defers to the server. The
`ModelManager` and `FirstRunWizard` routes share one `SetupFlowView` component.

#### Voice invite deferred to after first real conversation (#385)

Voice setup no longer blocks first-run. After the first real AI conversation
ends in a debrief, the app shows a one-time voice invite. Users who never want
voice are never asked about it during onboarding.

#### Setup docs rewrite (#386)

The published install and quickstart guides (`docs-site/.../start/`) describe the
actual shipped UI — the two-card Welcome, the background download pill, and Ollama
as an advanced option. A CI drift-prevention check (`scripts/check-docs-freshness.sh`)
compares each page's `verified_against` version against the release and fails the
release if any UI-referencing page has not been re-verified for the new minor.

#### Onboarding e2e suite as merge and release gate (#387)

`e2e/onboarding/` covers all eight journey paths (P1–P8) starting from a wiped
profile with no localStorage, no models, and no prior outcome. A mechanical
network-allowlist fixture blocks all non-loopback connections in every test.

| Journey | What it covers |
|---------|---------------|
| P1 | Full pipeline install → `status: ready` → session reachable |
| P2 | Scripted tutorial < 15 s → debrief → demo outcome |
| P3 | Ollama model → `llm-present` → `status: ready` |
| P4 | Local .gguf registered → `status: ready` |
| P5 | Remediation cards for disk-full / offline / checksum failures; text-only escape; forbidden-vocabulary invariant |
| P6 | Orphaned job on kill → relaunch → job re-attached |
| P7 | Regression: no fix action ever loops to Welcome (v0.2.2 regression guard) |
| P8 | `voice-ready` severity is `informational`; debrief reachable without voice |

The fast trio (P1, P2, P7) runs as a required check on every PR touching
onboarding code. The full P1–P8 matrix runs on all three platforms as a release
gate.

---

## Upgrade notes

No data migration required. If you have a `convsim.setup.complete` flag in
localStorage from v0.2.x, it is ignored; setup state is now read from
`GET /api/setup/status`.

---

# Conversation Simulator v0.2.1 — Release Notes

> **Patch release** — hotfix for the v0.2.0 Windows DOA (dead on arrival) bug.
> All Windows users on v0.2.0 must update; macOS and Linux are unaffected but
> are included in this release for consistency.

---

## What's fixed in v0.2.1

### [Bug] Windows: `convsim-core.exe` exited immediately on any invocation (#352)

Fresh v0.2.0 installs on Windows were broken: the sidecar process died the
instant it was launched (exit code 1, recovery card shown every time). The
root cause was an import-string passed to `uvicorn.run()` inside the
PyInstaller bundle.

**Root cause:** `main()` called `uvicorn.run("convsim_core.main:app", ...)`.
In a frozen PyInstaller executable the entry script runs as `__main__`, so
`convsim_core.main` is not present in the frozen importer's namespace. When
uvicorn tried to resolve the string via `importlib.import_module`, it raised
`ModuleNotFoundError` before the server ever bound a port. This was
undetectable in a standard developer-venv run, where the package is always
importable.

**Fix:** `main()` now passes the ASGI app object directly:
`uvicorn.run(app, ...)`. Since `reload=False` is the default, the import-string
indirection bought nothing; the object form is equivalent in behaviour and works
correctly inside a frozen executable.

**Regression guard added:** A new CI workflow (`binary-health-check.yml`) builds
the PyInstaller binary from source on Linux, macOS, and Windows and verifies
that the binary starts and answers `GET /api/health` within 10 s. This catches
any future recurrence of this class of frozen-importer regression.

---

# Conversation Simulator v0.1.0-alpha.1 — Release Notes

> **Alpha release** — This build is an early preview. Expect rough edges and
> breaking changes between alpha versions. File bugs at
> <https://github.com/outrightmental/ConversationSimulator/issues>.

---

## What's new in v0.1.0-alpha.1

This is the first public alpha of Conversation Simulator. Everything below is
new relative to the empty repository.

- **Text conversation loop** — Full session lifecycle: start a scenario, type
  player turns, receive NPC responses driven by a local LLM, watch live state
  meters, end the session, and receive a scored debrief. Runs entirely offline
  with the fake runtime; connects to a real model via llama.cpp when one is
  installed.
- **Four official scenario packs** — 16 playable scenarios across Job Interview
  Basics, Everyday Negotiation, Language Café, and Difficult Conversations. All
  packs are CC BY 4.0.
- **Pack schema and validator** — JSON Schema covering scenarios, NPCs, rubrics,
  scenes, and safety policies. The `convsim validate-pack` command catches
  malformed packs at import time and prints actionable errors.
- **Creator Workbench** — Browser UI for inspecting, editing, validating, and
  exporting scenario packs. No command-line skills required for pack authoring.
- **Model Manager** — Curated registry of local GGUF models with explicit
  license disclosure and SHA-256 checksum verification before loading.
- **Layered safety system** — Global non-overridable rules (minors, self-harm)
  enforced server-side, plus per-pack policies that packs can tighten but not
  weaken. Content cap at PG-13.
- **Cross-platform developer install** — `setup.sh` / `setup.ps1` and
  `dev.sh` / `dev.ps1` scripts tested on macOS, Linux x86_64, and Windows
  x86_64. Full pre-flight checks via `first-run-check.sh`.
- **CI and release infrastructure** — Three GitHub Actions workflows (CI,
  release build, release smoke matrix) covering all four platforms. Acceptance
  tests for player, creator, and developer journeys run in CI with the fake
  runtime.
- **Full documentation set** — Architecture, install, safety, privacy,
  scenario authoring, pack validation, runtime adapters, troubleshooting, and
  accessibility notes.

---

## Download and verify

This alpha ships as a **source install only**. The packaged desktop build does
not yet bundle `convsim-core`; follow the source build instructions below.

Future releases will publish installers. When they do, verify before running:

```bash
# macOS / Linux
shasum -a 256 <filename>
```

```powershell
# Windows PowerShell
Get-FileHash "<filename>" -Algorithm SHA256
```

Compare the output against `checksums-sha256.txt` attached to the release.

---

## System requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | macOS 12, Ubuntu 22.04, Windows 10 (build 19041+) | Latest stable |
| CPU | 64-bit x86 or Apple Silicon | Apple Silicon M1 or newer |
| RAM | 8 GB | 16 GB |
| Disk | 5 GB free | 20 GB free (headroom for multiple models) |
| Microphone | Optional | Required for voice input |

Run the pre-flight check before first launch:

```bash
./scripts/first-run-check.sh        # macOS / Linux
.\scripts\first-run-check.ps1       # Windows PowerShell
```

---

## Installation (source)

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh     # check env, install packages, create ~/.convsim/
./scripts/dev.sh       # start all services
```

Then open **http://127.0.0.1:7354** in your browser.

**Windows:** use `scripts\setup.ps1` and `scripts\dev.ps1` instead.

See [docs/install.md](docs/install.md) for full prerequisites and
[docs/platform-notes.md](docs/platform-notes.md) for platform-specific notes.

---

## Local model — not bundled

No language model weights are included. On first launch, the app opens the
**Model Manager**, which lists curated models with size, license, and hardware
requirements. You must accept the model license before a download begins. The
downloaded file is verified against its SHA-256 checksum before loading.

The recommended starter model is **Qwen3 4B Instruct Q4\_K\_M** (~2.5 GB,
Apache-2.0). The app is fully functional with the built-in fake runtime —
responses are scripted rather than generated, useful for testing and development
without any download.

| Model | Size | VRAM | License |
|---|---|---|---|
| Qwen3 4B Instruct Q4\_K\_M | 2.5 GB | 4 GB+ | Apache-2.0 |
| Qwen3 8B Instruct Q4\_K\_M | 5.0 GB | 6 GB+ | Apache-2.0 |
| Qwen3 14B Instruct Q4\_K\_M | 9.0 GB | 10 GB+ | Apache-2.0 |
| Mistral Small 3.1 24B Q4\_K\_M | 14.3 GB | 16 GB+ | Apache-2.0 |

---

## Privacy and safety

- **All inference runs locally.** No audio, text, or session data leaves your
  computer during play. The app requires internet access only for the initial
  model download and for optional pack updates.
- **No telemetry.** The app does not phone home, collect crash reports, or send
  usage statistics.
- **Content filtering.** The simulator applies keyword pre-checks and output
  validation before presenting NPC dialogue. See
  [docs/safety-policy.md](docs/safety-policy.md) for details.
- **Microphone permission.** The OS will prompt for microphone access on first
  use of voice input. You can use the app in text-only mode without granting
  this permission.
- **Session data stays on your machine.** Session transcripts and debrief
  reports are stored in `~/.convsim/` (macOS/Linux) or
  `%USERPROFILE%\.convsim\` (Windows). You can delete this directory at any
  time to remove all local data.

Verify the offline guarantee:

```bash
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic
```

---

## Known limitations in v0.1.0-alpha.1

- **Source install only.** There is no packaged installer in this alpha. The
  desktop app wrapper (`apps/desktop/`) exists but does not yet bundle
  `convsim-core`. Run the backend separately via `./scripts/dev.sh` — see
  [docs/install.md](docs/install.md).
- **No auto-update.** Download new releases manually from the releases page.
- **No code signing.** macOS Gatekeeper and Windows SmartScreen will warn about
  unverified publishers when a packaged build is eventually available.
- **Voice input and output** are implemented but require separate manual runtime
  setup: whisper.cpp for STT (`runtimes/whisper_cpp/`) and a local Kokoro
  server for TTS (`runtimes/kokoro/`). See the runtime READMEs for setup steps.
  The app runs fully in text-only mode without these runtimes.
- **Screenshots in the README are SVG placeholders**, not real UI recordings.
  They will be replaced with actual screen captures at the Milestone 1 polish
  stage.
- **No community pack browser.** Pack sharing requires manual zip export/import
  via the Creator Workbench. A discovery feed is planned post-alpha.
- **CPU-only inference is slow on large models.** On machines without a
  supported GPU, a single NPC turn with Qwen3 14B can take 60–120 seconds.
  The Qwen3 4B starter model is significantly faster and recommended for
  CPU-only setups.
- **Real-model smoke testing is manual.** CI runs all acceptance tests with the
  fake runtime. A real-model playthrough requires downloading a model (~2.5 GB
  minimum) and is not yet automated in CI.

For a full list of post-alpha work items, see
[docs/post-alpha-issues.md](docs/post-alpha-issues.md).

---

## Source build

To build from source on a clean checkout:

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh            # install deps, create Python venv
pnpm --filter @convsim/web build
# desktop build (future):
# pnpm --filter @convsim/desktop build
```

See [docs/install.md](docs/install.md) and
[docs/platform-notes.md](docs/platform-notes.md) for full prerequisites and
platform-specific notes.

---

## Reporting bugs

Open an issue at <https://github.com/outrightmental/ConversationSimulator/issues>.
Include:

- OS and version
- Output of `./scripts/first-run-check.sh` (or `first-run-check.ps1`)
- Log files from `~/.convsim/logs/`
- Steps to reproduce

For security vulnerabilities, follow the responsible disclosure process in
[SECURITY.md](SECURITY.md).
