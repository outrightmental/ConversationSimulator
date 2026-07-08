<!-- SPDX-License-Identifier: CC-BY-4.0 -->
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
  scenes, and safety policies. The `convsim-validate-pack` CLI catches malformed
  packs at import time and prints actionable errors.
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

The recommended starter model is **Qwen3 4B Instruct Q4\_K\_M** (~2.6 GB,
Apache-2.0). The app is fully functional with the built-in fake runtime —
responses are scripted rather than generated, useful for testing and development
without any download.

| Model | Size | VRAM | License |
|---|---|---|---|
| Qwen3 4B Instruct Q4\_K\_M | 2.6 GB | 4 GB+ | Apache-2.0 |
| Qwen3 8B Instruct Q4\_K\_M | 5.0 GB | 6 GB+ | Apache-2.0 |
| Qwen3 14B Instruct Q4\_K\_M | 9.0 GB | 10 GB+ | Apache-2.0 |
| Mistral Small 3.1 24B Q4\_K\_M | 14.8 GB | 16 GB+ | Apache-2.0 |

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
  fake runtime. A real-model playthrough requires downloading a model (~2.6 GB
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
