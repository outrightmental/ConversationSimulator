---
title: "Release checklist"
description: "Every gate a maintainer must complete before tagging a release: CI gates, manual smoke, acceptance suite, and Steam platform verification."
sidebar:
  order: 20
---

This checklist covers every step a maintainer must complete before tagging a
release.  It is split into three parts:

- **Part A — CI gates** (automated, no model downloads): must be green before
  any manual step begins.
- **Part B — Manual release smoke** (run on a clean profile): covers subsystems
  that require real services, a browser, and optionally real model weights.
- **Part C — Acceptance suite** (persona-specific checklists): player, creator,
  developer, and concept review gates that must pass before the MVP tag is applied.

Read Part A results in GitHub Actions before you touch Part B or Part C.

> **MVP release gate:** The release **cannot** be tagged as MVP unless every
> acceptance checklist under [`docs/acceptance/`](https://github.com/outrightmental/ConversationSimulator/tree/main/docs/acceptance) shows PASS (or a documented,
> maintainer-approved exception) in addition to Parts A and B below.

---

## Part A — CI gates (automated)

All of the following GitHub Actions workflows must be green on the commit you
intend to tag.

| Workflow | File | What it checks |
|---|---|---|
| CI | `.github/workflows/ci.yml` | Backend tests, frontend typecheck/test, schema and pack validation, acceptance tests |
| Release smoke — Linux x86_64 | `.github/workflows/release-smoke.yml` (job: `smoke-linux`) | All CI-subset subsystems on Ubuntu |
| Release smoke — macOS aarch64 | `.github/workflows/release-smoke.yml` (job: `smoke-macos / aarch64`) | All CI-subset subsystems on Apple Silicon |
| Release smoke — Windows x86_64 | `.github/workflows/release-smoke.yml` (job: `smoke-windows`) | All CI-subset subsystems on Windows |

**CI-subset subsystems (no model downloads, fake runtime):**

- [ ] `[setup]` — All expected monorepo paths present
- [ ] `[pack-valid]` — Official packs pass schema validation
- [ ] `[voice]` — Voice unavailable fallback tests pass (no TTS events when `tts_enabled=False`)
- [ ] `[health]` — Backend health unit tests pass (fake runtime)
- [ ] `[model-mgr]` — Model manager unit tests pass (no downloads)
- [ ] `[scenario-lib]` — Scenario library API unit tests pass
- [ ] `[text-session]` — Session create + turn pipeline unit tests pass
- [ ] `[debrief]` — Debrief engine unit tests pass
- [ ] `[offline]` — Network policy tests pass (no outbound calls during fake-runtime play)
- [ ] `[packaged-startup]` — Packaged startup unit tests pass (config resolution, no dev imports)
- [ ] `[e2e-playthrough]` — End-to-end scripted playthrough passes in packaged-env mode
- [ ] `[web]` — Web frontend typecheck passes

> **Note:** `[artifact-inspect]` skips in CI (no build artifact available).  It
> runs automatically as part of the Steam deploy workflow, and can be triggered
> manually via `--full` mode — see Part F below.

If any CI gate is red, **do not proceed to Part B** — fix the failure first.

---

## Part B — Manual release smoke

Run this on a **clean profile** (fresh `~/.convsim/` directory or a new user
account) to catch first-run issues that don't appear on development machines.

### Minimum hardware for real-model smoke

| Item | Minimum | Recommended |
|---|---|---|
| OS | macOS 13, Ubuntu 22.04, Windows 10 build 19041 | Latest stable |
| CPU | 64-bit x86 or Apple Silicon | Apple Silicon M2 or newer |
| RAM | 8 GB | 16 GB |
| Disk free | 10 GB | 20 GB |
| VRAM | 0 GB (CPU fallback) | 4 GB (for starter model on GPU) |
| Microphone | Optional | Required for voice smoke |

Record your hardware and runtime details in the **smoke log** at the bottom of
this checklist.

### B.1 Pre-flight

```bash
# macOS / Linux
./scripts/first-run-check.sh

# Windows PowerShell
.\scripts\first-run-check.ps1
```

- [ ] All `FAIL` items resolved (warnings may remain for optional hardware)
- [ ] Ports 7354–7358 are free

### B.2 Setup

```bash
# macOS / Linux
./scripts/setup.sh

# Windows PowerShell
.\scripts\setup.ps1
```

- [ ] Setup completes without errors
- [ ] Python venv created at `services/convsim-core/.venv/`
- [ ] `node_modules` installed at repo root and in workspaces

### B.3 Backend health

```bash
# macOS / Linux
./scripts/dev.sh     # keep running in a separate terminal

# Windows PowerShell
.\scripts\dev.ps1    # keep running in a separate terminal
```

Then:

```bash
curl http://127.0.0.1:7355/api/health | python3 -m json.tool
```

- [ ] `status` is `"ok"`
- [ ] `database.status` is `"ok"`
- [ ] `runtime.status` is `"ready"` (fake runtime on source install is expected)
- [ ] `stt.status` and `tts.status` fields are present (value may be `"unavailable"` without runtimes installed)

### B.4 Web launch

Open `http://127.0.0.1:7354` in the browser.

- [ ] Home screen loads without console errors
- [ ] Service status indicators (convsim-core, LLM runtime) show correct state
- [ ] No "Failed to fetch" errors in the network tab

**Desktop wrapper** (if testing a desktop build):

```bash
# macOS / Linux
./scripts/dev-desktop.sh

# Windows PowerShell
.\scripts\dev-desktop.ps1
```

- [ ] Desktop window opens and renders the web UI
- [ ] Title bar shows "Conversation Simulator"

### B.5 Model manager (fake mode)

In the browser, navigate to **Settings → Models**.

- [ ] Model list loads without errors (fake runtime shows no downloadable models or a stub list)
- [ ] No download is triggered automatically
- [ ] License acceptance dialog appears before any download button becomes active

**Real-model smoke** (optional, requires adequate hardware):

- [ ] Download the **Qwen3 4B Instruct Q4_K_M** starter model (≈2.6 GB)
- [ ] SHA-256 checksum verified by the app after download
- [ ] Model status changes to `"loaded"` after checksum passes
- [ ] Record model filename and size in the smoke log

### B.6 Scenario library

In the browser, navigate to **Scenarios** or equivalent library view.

- [ ] At least one official pack is listed (e.g. "Job Interview Basics")
- [ ] Expanding a pack shows individual scenarios
- [ ] Scenario card shows title, description, and difficulty tag

### B.7 Text session

Select **Job Interview Basics → Behavioral Interview** and start a session.

- [ ] Session starts and NPC opening line is delivered within 10 seconds
- [ ] Type a player turn and submit — NPC responds within 30 seconds (fake runtime) / 60 seconds (real model, CPU)
- [ ] Session transcript updates correctly after each turn
- [ ] Session can be ended cleanly with the Stop / End Session button

### B.8 Debrief

After ending the session, navigate to the debrief screen.

- [ ] Debrief report loads (may show minimal data for a one-turn session)
- [ ] Rubric scores are displayed (even if zero for short sessions)
- [ ] Export / Download option is present

### B.9 Pack validation

```bash
# macOS / Linux
node packages/scenario-schema/tests/validate-packs.js packs/official

# Windows PowerShell
node packages\scenario-schema\tests\validate-packs.js packs\official
```

- [ ] Exits 0 with no validation errors

Full policy check (requires `convsim-core` installed):

```bash
for d in packs/official/*/; do
    convsim-validate-pack "$d"
done
```

- [ ] All packs pass policy validation

### B.10 Voice fallback (voice unavailable path)

> This step tests the path where voice is explicitly disabled. It does **not**
> require a microphone or audio hardware.

```bash
cd services/convsim-core
python -m pytest tests/test_voice_smoke.py -v -k "fallback"
```

- [ ] All fallback tests pass
- [ ] No `tts_audio_chunk` events appear in TTS-disabled sessions

**Voice with real runtimes** (optional, requires microphone + whisper.cpp + Kokoro):

```bash
# Install runtimes first — see runtimes/whisper_cpp/README.md and runtimes/kokoro/README.md
CONVSIM_STT_WORKER_ID=whisper_cpp \
CONVSIM_TTS_WORKER_ID=kokoro \
python -m pytest tests/test_voice_smoke.py -v
```

- [ ] English path (`behavioral_interview`) passes end-to-end
- [ ] Spanish path (`spanish_coffee`) passes end-to-end
- [ ] STT returns a non-empty transcript for a real audio recording
- [ ] TTS returns audio chunks with a non-null `cache_path`
- [ ] Push-to-talk voice input works via the web UI (manual, requires microphone)

### B.11 Steam Cloud sync verification

**Applies to Steam builds only.** Skip this step on non-Steam (direct-download)
builds.  Requires two machines or two Steam accounts / profiles with the same
Steam app installed.

#### B.11.1 Verify the sync file placement

On the test machine, launch the app under Steam and select a model in the Model
Manager.  Wait 5 seconds for the debounce to flush, then close the app.

```bash
# macOS
cat "$HOME/Library/Application Support/com.outrightmental.convsim/steam_cloud_settings.json"

# Linux / Steam Deck
cat "$HOME/.local/share/convsim/steam_cloud_settings.json"

# Windows (PowerShell)
type "$env:LOCALAPPDATA\outrightmental\convsim\steam_cloud_settings.json"
```

- [ ] File exists at the data root (not inside `db/`, `logs/`, or any other subdirectory)
- [ ] File contains only `last_model_id` — no transcripts, audio paths, or session content

#### B.11.2 Verify subdirectory exclusion markers

```bash
# macOS / Linux (check each subdirectory for .nosteamcloudpath).
# Note: the model marker lives at models/llm/ — models_dir resolves to
# {data_root}/models/llm, so the marker is placed there, not at models/.
for d in data db logs models/llm packs exports cache crashes; do
    echo "$d: $(ls "$HOME/Library/Application Support/com.outrightmental.convsim/$d/.nosteamcloudpath" 2>/dev/null && echo PRESENT || echo MISSING)"
done
```

- [ ] `.nosteamcloudpath` is present in every marked subdirectory (`data/`, `db/`, `logs/`, `models/llm/`, `packs/`, `exports/`, `cache/`, `crashes/`)
- [ ] No `.nosteamcloudpath` marker exists at the data root itself (that would prevent the cloud settings file from syncing)

#### B.11.3 Cross-device sync test

- [ ] On machine A: select a model in the Model Manager, close the app, and wait for Steam to sync (Steam tray icon stops animating, typically 10–30 seconds)
- [ ] On machine B (fresh profile or second machine): launch the app via Steam
- [ ] Confirm the same model is pre-selected in the Model Manager on machine B
- [ ] Confirm that no conversation transcripts, session history, audio recordings, or private pack data appears on machine B
- [ ] Confirm the Steam Cloud section in Settings (Settings → Steam Cloud sync) shows "Steam Cloud is active for this session"

### B.12 Offline smoke

Confirms no outbound network calls occur during a scripted play session.

```bash
# Build the CLI if not already built:
pnpm --filter @convsim/cli build

# Run offline smoke:
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic
```

- [ ] Exits 0 — no outbound connections detected
- [ ] Session completes with fake runtime without touching the network

> The offline smoke is a **release gate** — this check must pass before the
> release is tagged.

---

## Part C — Acceptance suite

Complete the persona-specific checklists before applying the MVP tag.
Detailed rubrics, automated test references, and sign-off tables live in:

| Checklist | File | Owner | Automated test |
|---|---|---|---|
| Player | `docs/acceptance/player-checklist.md` | Platform team | `tests/acceptance/test_player_text_path.py` |
| Creator | `docs/acceptance/creator-checklist.md` | Content team | `tests/acceptance/test_creator_flow.py` |
| Developer | `docs/acceptance/developer-checklist.md` | DX team | `tests/acceptance/test_developer_flow.py` |
| Concept review | `docs/acceptance/concept-review.md` | Product team | manual only |

Run the automated portion from the repo root:

```bash
python -m pytest tests/acceptance/ -v
```

Summary sign-off:

| Checklist | Automated | Manual | Sign-off | Date |
|---|---|---|---|---|
| Player | ☐ | ☐ | | |
| Creator | ☐ | ☐ | | |
| Developer | ☐ | ☐ | | |
| Concept review | n/a | ☐ | | |

All four checklists must reach PASS (or PARTIAL with documented, maintainer-approved exception) before the release is tagged MVP.

---

## Part D — Platform coverage matrix

Mark which platforms were manually tested for this release.

| Platform | Source / dev | Desktop build | Tester | Date |
|---|---|---|---|---|
| macOS (Apple Silicon) | ☐ | ☐ | | |
| macOS (Intel) | ☐ | ☐ | | |
| Linux x86_64 | ☐ | ☐ | | |
| Windows x86_64 | ☐ | ☐ | | |

At least one platform must complete the full Part B checklist with a real model
before the release is published.  CI covers all platforms in fake-runtime mode.

---

## Part E — Windows Steam install verification

Run this checklist on a **clean Windows machine** (a fresh Steam library
directory with no prior Conversation Simulator install) before submitting a
Windows depot to Valve.  It supplements Part B by testing the Steam-specific
install path rather than the source-checkout developer path.

Minimum hardware: see "Windows system requirements for Steam" in
[`docs/platform-notes.md`](/play/platform-notes/).

### E.1 Fresh install from Steam

1. Install the app from the Steam client (or use `steamcmd +app_update <AppID>`
   on a test machine).
2. Steam installs files into the Steam library directory (e.g.
   `C:\Program Files (x86)\Steam\steamapps\common\ConversationSimulator\`).
3. Launch via the Steam Play button (or double-click `ConversationSimulator.exe`
   from the install directory).

- [ ] Steam installs without errors
- [ ] No Python, Node.js, or Rust prompts appear during install
- [ ] `ConversationSimulator.exe` launches from the Steam Play button
- [ ] The Tauri window opens and displays the home screen
- [ ] No terminal window is visible (convsim-core runs as a hidden child process)
- [ ] No SmartScreen or antivirus warning blocks launch (signed build only)

### E.2 First-run model wizard

On first launch, the Model Manager wizard should appear automatically.

- [ ] Wizard is shown before the main scenario library is accessible
- [ ] All six mandatory disclosure fields are visible:
  model name, source URL, license, download size, SHA-256 checksum,
  destination path on disk
- [ ] Download button is inactive until the player confirms disclosure
- [ ] Destination path shown is under `%LOCALAPPDATA%\outrightmental\convsim\models\`
  (not under `%USERPROFILE%\.convsim\` — that would indicate a stale migration)
- [ ] Download completes, SHA-256 is verified, model status changes to `loaded`

### E.3 Text scenario and debrief

Select **Job Interview Basics → Behavioral Interview** and run a session.

- [ ] Scenario library loads and all five official packs are listed
  (Job Interview Basics, Everyday Negotiation, Language Café,
  Difficult Conversations, Dating — Confidence & Boundaries)
- [ ] Session starts without errors; NPC opening line is delivered
- [ ] Player can submit a text turn; NPC responds within 60 seconds (CPU-only)
- [ ] Session ends cleanly via the Stop / End Session button
- [ ] Debrief screen loads with rubric scores and an export option
- [ ] Exporting the transcript saves a file to `%LOCALAPPDATA%\outrightmental\convsim\exports\`

### E.4 Log verification

After running a session, confirm logs are written to the expected location.

```powershell
# Expected location (platform-native, not the old ~/.convsim path)
Get-ChildItem "$env:LOCALAPPDATA\outrightmental\convsim\logs\"
```

- [ ] Log files are present in `%LOCALAPPDATA%\outrightmental\convsim\logs\`
- [ ] Logs contain no API keys, tokens, or PII
- [ ] No log files exist under `%USERPROFILE%\.convsim\` on a fresh install
  (if they do, it indicates the migration from a prior alpha install occurred —
  verify the migration marker `.convsim_migrated_to_platform_dir` exists in
  `%USERPROFILE%\.convsim\`)

### E.5 Uninstall behavior

Uninstall via **Steam → right-click → Manage → Uninstall**.

- [ ] Uninstall completes without errors
- [ ] The Steam library directory for the app is removed
- [ ] User data under `%LOCALAPPDATA%\outrightmental\convsim\` is **preserved**
  (session history, downloaded models, exported transcripts must survive an
  uninstall — Steam uninstallers must not touch `%LOCALAPPDATA%`)
- [ ] Downloaded model weights are still present at
  `%LOCALAPPDATA%\outrightmental\convsim\models\` after uninstall

### E.6 Reinstall behavior

Reinstall the app from Steam after the E.5 uninstall.

- [ ] Reinstall completes without errors
- [ ] On launch, **no first-run wizard** appears — the app detects existing
  user data and goes directly to the main screen
- [ ] Session history from before the uninstall is accessible in the library
- [ ] Downloaded model is detected as `loaded` (no re-download needed)
- [ ] Logs from the new session are appended to the existing log directory

### E.7 Depot content audit (pre-submission)

Before submitting the depot to Valve, run the audit locally:

```powershell
.\scripts\depot-audit.ps1 steam-content\windows
```

- [ ] Exits 0 (no violations)
- [ ] No `.gguf`, `.bin`, `.safetensors`, `.pt`, `.pth`, or `.ckpt` files in the depot
- [ ] No `.env`, `__pycache__\`, or `.venv\` directories in the depot
- [ ] Installer is Authenticode-signed (verify with `signtool.exe verify /pa /v <file>`)

### E.8 Offline play after model download

Block all outbound network access (Windows Firewall or disconnect the network
adapter) after the model has been downloaded and verified, then start a session.

- [ ] Session starts and runs normally with no network connection
- [ ] No error or network-related warning appears in the UI
- [ ] Push-to-talk (if voice is enabled) still functions locally
- [ ] Reconnecting the network does not trigger any sync or phone-home behavior

### E.9 Privacy controls

Navigate to **Settings → Privacy** (or the Privacy section of Settings).

- [ ] Transcript history view is accessible and lists the sessions played above
- [ ] "Clear all local data" button is present and functional
- [ ] Local data path (`%LOCALAPPDATA%\outrightmental\convsim\`) is displayed in the UI
- [ ] Clearing data removes all sessions from the session library without requiring
  file-manager navigation
- [ ] After clearing, `GET /api/health` shows `privacy.telemetry_enabled: false`
- [ ] No outbound telemetry call is observed before or after clearing data

### E.10 Steam Cloud exclusions

See **Part B.11** for the full Steam Cloud sync verification procedure.
Complete B.11 on this Windows machine before checking the items below.

- [ ] B.11 Steam Cloud sync verification completed (Windows)
- [ ] `steam_cloud_settings.json` contains only `last_model_id` — no transcripts,
  audio paths, or session content
- [ ] `.nosteamcloudpath` markers present in `data\`, `db\`, `logs\`,
  `models\llm\`, `packs\`, `exports\`, `cache\`, and `crashes\` subdirectories

### E.11 Support bundle flow

Navigate to **Settings → Support** (or the Help / Support screen).

- [ ] Log directory path is shown or linked in the UI
- [ ] User can copy the log path without file-manager navigation
- [ ] Opening the log directory via the UI shows `%LOCALAPPDATA%\outrightmental\convsim\logs\`
- [ ] Log files contain startup events and session lifecycle info with no raw
  conversation text or NPC responses

### E.12 Achievements, stats, and rich presence (if included in build)

> Skip this step if the build was not compiled with `--features steam`.
> Steam features are active only when the Tauri command `get_steam_status`
> returns `is_steam_enabled: true` in its `SteamStatus` payload
> (`{"is_steam_enabled": ..., "launched_by_steam": ..., "app_id": ...,
> "persona_name": ...}`).  `is_steam_enabled` is `true` only when the build
> includes the `steam` Cargo feature **and** the app was launched from a
> running Steam client.  As a UI cross-check, the Settings → Steam Cloud
> panel shows an "active" indicator whenever the app is `launched_by_steam`.

- [ ] Completing a scored session triggers the expected achievement notification
  (Steam overlay toast or in-app indicator)
- [ ] Steam overlay (Shift+Tab) shows the unlocked achievement in the
  overlay's achievement list
- [ ] Rich presence text in the Steam Friends list reflects the current
  scenario or session state
- [ ] No outbound HTTP calls outside the Steamworks SDK are observed during play

---

## Part F — Packaged-app smoke (desktop build)

Run this checklist against an **actual packaged desktop build** (`.app`,
`.AppImage`, or `.exe` installer) on a machine with no source checkout.
It supplements Part B by testing the packaged binary path rather than the
source-install developer path.

> **CI equivalent:** `[e2e-playthrough]` in [`release-smoke.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/workflows/release-smoke.yml) covers the
> fake-runtime version of this flow.  Part F validates the same flow with a
> real packaged binary and (optionally) a real model.

### F.1 Build and locate the packaged binary

```bash
# Build the convsim-core PyInstaller binary and place it in resources/bin/:
./scripts/build-core.sh

# Then build the full Tauri desktop app:
pnpm --filter @convsim/desktop build

# The installer is at:
# Linux:   apps/desktop/src-tauri/target/release/bundle/appimage/*.AppImage
# macOS:   apps/desktop/src-tauri/target/release/bundle/macos/*.app
# Windows: apps/desktop/src-tauri/target/release/bundle/nsis/*.exe
```

### F.2 Artifact inspection

Run the artifact inspection test suite against the built artifact directory.
Checks depot layout, executable permissions, icon presence, version stamping,
and forbidden file patterns.

```bash
# Linux AppImage example:
CONVSIM_ARTIFACT_DIR=apps/desktop/src-tauri/target/release/bundle/appimage \
  python -m pytest tests/artifact/ -v

# macOS .app example (inspect the .app bundle directory):
CONVSIM_ARTIFACT_DIR=apps/desktop/src-tauri/target/release/bundle/macos \
  python -m pytest tests/artifact/ -v

# Windows (inspect the NSIS installer directory):
$env:CONVSIM_ARTIFACT_DIR = "apps\desktop\src-tauri\target\release\bundle\nsis"
python -m pytest tests/artifact/ -v

# Or via the release-smoke --full runner (all checks in one command):
CONVSIM_ARTIFACT_DIR=<artifact-dir> ./scripts/release-smoke.sh --full
```

- [ ] `[artifact-inspect]` passes — no violations found
- [ ] Version number in installer filename matches the release tag
- [ ] macOS `.app` `Contents/Info.plist` `CFBundleShortVersionString` is stamped
- [ ] Version is not `0.0.0` (confirms the stamp step ran)
- [ ] Linux `.AppImage` has executable bit set (`chmod +x` if missing)
- [ ] macOS `.app` main binary is executable
- [ ] macOS `.app` contains an `.icns` icon in `Contents/Resources/`
- [ ] No `.gguf`, `.safetensors`, `.pt`, `.pth`, or `.ckpt` files present
- [ ] No `.env`, `pytest.ini`, `__pycache__/`, or `tests/` present

### F.3 Launch and confirm core health

**macOS / Linux:**

```bash
# Set CONVSIM_BUNDLED_RUNTIME_DIR if the runtimes are not in the default location.
open "ConversationSimulator.app"          # macOS
./ConversationSimulator-*.AppImage        # Linux

# Wait ~5 seconds for the sidecar to start, then:
curl http://127.0.0.1:7355/api/health | python3 -m json.tool
```

**Windows:**

```powershell
Start-Process "Conversation Simulator_*.exe"
# Wait ~5 seconds, then:
Invoke-RestMethod http://127.0.0.1:7355/api/health | ConvertTo-Json
```

- [ ] Desktop window opens and renders the web UI
- [ ] Title bar shows "Conversation Simulator"
- [ ] `GET /api/health` returns `{"status": "ok", ...}`
- [ ] No terminal window visible (sidecar runs as hidden child process)

### F.4 Scripted text playthrough (fake runtime)

With no real model installed, the app should fall back to the fake runtime.

In the desktop app:

- [ ] Home screen loads without console errors
- [ ] At least one official pack is listed in the Scenarios library
- [ ] `behavioral_interview` scenario is present
- [ ] Starting a session delivers an NPC opening line (fake runtime response)
- [ ] Three scripted player turns complete without error
- [ ] Session ends cleanly via the Stop / End Session button
- [ ] Debrief screen loads with rubric scores and export option

### F.5 Scripted text playthrough (real model — optional)

Requires the **Qwen3 4B Instruct Q4_K_M** starter model (≈2.6 GB) to be
downloaded and verified via the in-app Model Manager.

- [ ] First-run Model Manager wizard appeared before the scenario library
- [ ] Disclosure fields (name, URL, license, size, SHA-256, destination) visible
- [ ] Download completed; SHA-256 verified; model status changed to `loaded`
- [ ] NPC opening line delivered within 60 seconds (CPU inference)
- [ ] Three scripted player turns complete; each NPC response within 60 seconds
- [ ] Session ends cleanly; debrief shows real rubric scores

### F.6 Transcript privacy verification

After running a test session, confirm no transcript content escaped into
the failure artifact directory (CI / local `$TMPDIR/convsim-release-smoke-*/`).

```bash
# Inspect the artifact directory for transcript-like content:
ls -la "${TMPDIR:-/tmp}"/convsim-release-smoke-*/
grep -r "player_turn\|npc_turn\|content.*:" "${TMPDIR:-/tmp}"/convsim-release-smoke-*/ \
  2>/dev/null || echo "No transcript content found in artifacts"
```

- [ ] No `player_turn` or `npc_turn` event content in any artifact file
- [ ] `save_transcript: false` was set in all smoke session configs (see [`tests/e2e/test_scripted_playthrough.py`](https://github.com/outrightmental/ConversationSimulator/blob/main/tests/e2e/test_scripted_playthrough.py))

---

## Part G — macOS Steam beta install verification

Run this checklist on a **clean macOS machine** (fresh Steam library, no prior
Conversation Simulator data) before declaring the macOS Stage 3 gate open.
It is the macOS equivalent of Part E.

Minimum hardware: macOS 13 Ventura or newer, Apple Silicon (arm64) or Intel
(x86-64).  See [`docs/platform-notes.md`](/play/platform-notes/) for system requirements.

### G.1 Gatekeeper and notarization

Install the app from the Steam client and attempt to launch it on a fresh macOS
profile where the app has never been opened before.

- [ ] Steam installs the macOS app without errors (no Python, Node.js, or Rust prompts)
- [ ] The `.app` bundle opens from the Steam Play button **without** a Gatekeeper
  "unverified developer" dialog (notarised + stapled build)
- [ ] `spctl --assess --verbose "ConversationSimulator.app"` exits 0 and prints
  `accepted` (run in Terminal on the installed `.app`)
- [ ] `codesign --verify --deep --strict "ConversationSimulator.app"` exits 0
- [ ] No persistent security exception in System Settings → Privacy & Security
  is required after first launch

### G.2 Fresh install from Steam

- [ ] Tauri window opens and displays the home screen
- [ ] No terminal window is visible (convsim-core runs as a hidden child process)
- [ ] `~/Library/Application Support/com.outrightmental.convsim/` is created on
  first launch; no data written before the first-run wizard is dismissed

### G.3 First-run model wizard

- [ ] Wizard is shown before the main scenario library is accessible
- [ ] All six mandatory disclosure fields are visible:
  model name, source URL, license, download size, SHA-256 checksum,
  destination path on disk
- [ ] Download button is inactive until the player confirms disclosure
- [ ] Destination path shown is under
  `~/Library/Application Support/com.outrightmental.convsim/models/`
- [ ] Download completes; SHA-256 is verified; model status changes to `loaded`

### G.4 Text scenario and debrief

Select **Job Interview Basics → Behavioral Interview** and run a session.

- [ ] Scenario library loads and all five official packs are listed
- [ ] Session starts without errors; NPC opening line is delivered
- [ ] Player can submit a text turn; NPC responds within 60 seconds (CPU-only)
- [ ] Session ends cleanly via the Stop / End Session button
- [ ] Debrief screen loads with rubric scores and an export option
- [ ] Exporting the transcript saves a file under
  `~/Library/Application Support/com.outrightmental.convsim/exports/`

### G.5 Offline play after model download

Disconnect the network (Wi-Fi off or Airplane mode) after the model is
downloaded and verified.

- [ ] Session starts and runs normally with no network connection
- [ ] No error or network-related warning appears
- [ ] Reconnecting to the network does not trigger any sync or phone-home behavior

### G.6 Privacy controls

Navigate to **Settings → Privacy**.

- [ ] Transcript history view lists the sessions played above
- [ ] "Clear all local data" button is present and functional
- [ ] Local data path (`~/Library/Application Support/com.outrightmental.convsim/`)
  is displayed in the UI
- [ ] Clearing data removes all sessions without requiring Finder navigation
- [ ] `telemetry_enabled` is `false` in `GET /api/health`

### G.7 Steam Cloud exclusions

See **Part B.11** for the full Steam Cloud sync verification procedure.

- [ ] B.11 Steam Cloud sync verification completed (macOS)
- [ ] `steam_cloud_settings.json` at the data root contains only `last_model_id`
- [ ] `.nosteamcloudpath` markers present in `data/`, `db/`, `logs/`,
  `models/llm/`, `packs/`, `exports/`, `cache/`, and `crashes/`

### G.8 Support bundle flow

Navigate to **Settings → Support**.

- [ ] Log directory path is shown or linked in the UI
- [ ] Opening the log directory via the UI reveals
  `~/Library/Application Support/com.outrightmental.convsim/logs/`
- [ ] Log files contain startup events and session lifecycle info with no raw
  conversation text

### G.9 Achievements, stats, and rich presence (if included in build)

> Skip if `get_steam_status` returns `is_steam_enabled: false` (see E.12).

- [ ] Completing a scored session triggers an achievement notification
- [ ] Steam overlay (Shift+Tab) reflects the unlocked achievement
- [ ] Rich presence text updates to reflect the current session state
- [ ] No outbound HTTP calls outside the Steamworks SDK observed during play

### G.10 Log verification

```bash
ls -la "$HOME/Library/Application Support/com.outrightmental.convsim/logs/"
```

- [ ] Log files present in the macOS data directory
- [ ] Logs contain no API keys, tokens, or raw conversation content
- [ ] No stale `~/.convsim/` directory was created (macOS platform path only)

### G.11 Uninstall and reinstall behavior

Uninstall via **Steam → right-click → Manage → Uninstall**, then reinstall.

- [ ] Uninstall completes; the Steam library directory for the app is removed
- [ ] User data under `~/Library/Application Support/com.outrightmental.convsim/`
  is **preserved** (Steam uninstallers must not touch Application Support)
- [ ] Downloaded model weights survive the uninstall
- [ ] After reinstall, **no first-run wizard** appears — the app detects existing
  user data and goes directly to the main screen
- [ ] Session history and downloaded model detected as `loaded` (no re-download)

---

## Part H — Linux / SteamOS Steam beta install verification

Run this checklist on a **clean Ubuntu 22.04 or SteamOS 3.x machine** with
no prior Conversation Simulator install.  It is the Linux equivalent of Part E.

### H.1 Executable permissions and dependency verification

```bash
# After Steam installs the app:
INSTALL_DIR="$HOME/.steam/steam/steamapps/common/ConversationSimulator"
ls -la "$INSTALL_DIR"

# Check the AppImage is executable:
file "$INSTALL_DIR/ConversationSimulator.AppImage"   # should say "ELF 64-bit" or "AppImage"

# Confirm glibc version meets the ≥ 2.35 requirement:
ldd --version | head -1
```

- [ ] AppImage file is present in the Steam install directory
- [ ] AppImage has the executable bit set (`-rwxr-xr-x`)
- [ ] `ldd --version` reports glibc ≥ 2.35 (Ubuntu 22.04 ships 2.35; SteamOS 3.x ships 2.37+)
- [ ] No additional package install prompts appear (WebKitGTK and GTK 3 bundled
  in AppImage)
- [ ] On Ubuntu 22.04 without FUSE 2: AppImage runs with `--appimage-extract-and-run`
  flag or after `sudo apt-get install libfuse2`

### H.2 Fresh install from Steam

- [ ] Tauri window opens and displays the home screen
- [ ] No terminal window visible (convsim-core runs as hidden child process)
- [ ] `~/.local/share/convsim/` (or `$XDG_DATA_HOME/convsim` when `XDG_DATA_HOME`
  is set) is created on first launch (platform-native data directory; confirm in
  startup log)

### H.3 First-run model wizard

- [ ] Wizard is shown before the main scenario library is accessible
- [ ] All six mandatory disclosure fields visible (name, source, license, size,
  SHA-256, destination path)
- [ ] Download button inactive until disclosure confirmed
- [ ] Destination path shown is under `~/.local/share/convsim/models/`
- [ ] Download completes; SHA-256 verified; model status changes to `loaded`

### H.4 Text scenario and debrief

Select **Job Interview Basics → Behavioral Interview** and run a session.

- [ ] All five official packs listed in the scenario library
- [ ] Session starts; NPC opening line delivered
- [ ] Player text turn submitted; NPC responds within 60 seconds (CPU-only)
- [ ] Session ends cleanly; debrief screen loads with rubric scores and export option
- [ ] Exported transcript saved under `~/.local/share/convsim/exports/`

### H.5 Offline play after model download

Disable the network interface (`nmcli networking off` or unplug ethernet) after
model download.

- [ ] Session runs normally with no network
- [ ] No error or network-related warning in the UI
- [ ] Restoring network does not trigger phone-home or sync behavior

### H.6 Privacy controls

Navigate to **Settings → Privacy**.

- [ ] Transcript history view lists played sessions
- [ ] "Clear all local data" button present and functional
- [ ] Local data path displayed in the UI
- [ ] Clearing data removes sessions without terminal navigation
- [ ] `telemetry_enabled` is `false` in `GET /api/health`

### H.7 Steam Cloud exclusions

See **Part B.11** for the full Steam Cloud sync verification procedure.

- [ ] B.11 Steam Cloud sync verification completed (Linux)
- [ ] `steam_cloud_settings.json` at the data root contains only `last_model_id`
- [ ] `.nosteamcloudpath` markers present in all required subdirectories

### H.8 Support bundle flow

Navigate to **Settings → Support**.

- [ ] Log directory path shown or linked in the UI
- [ ] Opening via the UI confirms logs in `~/.local/share/convsim/logs/`
- [ ] Log files contain diagnostic context with no raw conversation text

### H.9 Achievements, stats, and rich presence (if included in build)

> Skip if `get_steam_status` returns `is_steam_enabled: false` (see E.12).

- [ ] Completing a scored session triggers an achievement notification
- [ ] Steam overlay (Shift+Tab) reflects the unlocked achievement
- [ ] Rich presence text updates in the Steam Friends list
- [ ] No outbound HTTP calls outside the Steamworks SDK during play

### H.10 Log verification

```bash
ls -la ~/.local/share/convsim/logs/
```

- [ ] Log files present
- [ ] No API keys, tokens, or raw conversation content in logs
- [ ] No stale `~/.convsim/` directory (platform-native path only)

### H.11 FUSE and AppImage behavior notes

> Document any FUSE-related issues encountered during this verification.

| Issue | Resolution | Documented |
|-------|-----------|-----------|
| FUSE 2 not present | Run with `--appimage-extract-and-run` or `apt install libfuse2` | [ ] |
| AppImage not executable | `chmod +x ConversationSimulator.AppImage` | [ ] |
| WebKit / GTK missing | Should not occur (bundled); document if observed | [ ] |

---

## Part I — Steam Deck beta verification

Run this checklist on **physical Steam Deck hardware** running SteamOS 3.x in
Gaming Mode.  This is required for the Stage 4 gate G4-02 (Steam Deck Verified).

All steps must be completable without a keyboard or mouse: use the D-pad,
A/B/X/Y buttons, left stick, right trackpad, and the Steam on-screen keyboard
only.  See [`docs/QA_STEAM_PLATFORM_MATRIX.md §3`](/dev/qa-steam-platform-matrix/) for the Steam Deck
verification checklist and §4 for the TC-11 test case that these steps exercise.

### I.1 Install from Steam library

In Gaming Mode on the Steam Deck:

- [ ] App is listed in the Steam library after the beta key is redeemed
- [ ] Install completes from the Steam Play button without switching to Desktop Mode
- [ ] App launches in Gaming Mode from the library tile

### I.2 First-run model wizard (controller-only)

- [ ] Wizard appears before the main scenario library
- [ ] Model Manager UI is fully navigable with D-pad and A/B/X/Y buttons
- [ ] On-screen keyboard appears automatically when any text field is focused
  (tester name or search field)
- [ ] Download button can be reached and activated via controller alone
- [ ] Download completes; model status changes to `loaded` at the expected
  SteamOS latency (see [`docs/linux-steamos-requirements.md`](/play/linux-steamos/) — target ≤ 90 s
  for Qwen3 4B Q4_K_M on Steam Deck hardware)

### I.3 Controller-only full session (TC-11)

Complete all 13 steps of TC-11 from [`docs/QA_STEAM_PLATFORM_MATRIX.md §4`](/dev/qa-steam-platform-matrix/)
using the controller alone.

| TC-11 step | Result |
|-----------|--------|
| 11.1 Launch and reach Home screen | [ ] PASS / [ ] FAIL |
| 11.2 Navigate Home with D-pad / left stick | [ ] PASS / [ ] FAIL |
| 11.3 Navigate to Scenario Library | [ ] PASS / [ ] FAIL |
| 11.4 Select scenario without keyboard/mouse | [ ] PASS / [ ] FAIL |
| 11.5 On-screen keyboard for text field | [ ] PASS / [ ] FAIL |
| 11.6 Start voice session; R1 triggers push-to-talk | [ ] PASS / [ ] FAIL / [ ] N/A |
| 11.7 Submit text turn via on-screen keyboard | [ ] PASS / [ ] FAIL |
| 11.8 End session; reach Debrief screen | [ ] PASS / [ ] FAIL |
| 11.9 Navigate Debrief; check readability at 1280×800 | [ ] PASS / [ ] FAIL |
| 11.10 Navigate Model Manager, Settings, Support, Workbench | [ ] PASS / [ ] FAIL |
| 11.11 DebugDrawer excluded from focus ring (dev build) | [ ] PASS / [ ] N/A |
| 11.12 Steam overlay opens / closes without breaking session | [ ] PASS / [ ] FAIL |
| 11.13 Quit via controller; no orphaned processes | [ ] PASS / [ ] FAIL |

### I.4 Offline play under SteamOS

After model download, switch to Airplane Mode (Steam Deck Quick Access → Network).

- [ ] Session runs normally with no network
- [ ] No error or network-related warning in the UI (controller-accessible)
- [ ] TC-09 offline smoke criteria met on SteamOS hardware

### I.5 Privacy controls and support bundle

Navigate to **Settings → Privacy** and **Settings → Support** via controller.

- [ ] Privacy controls navigable without keyboard/mouse
- [ ] "Clear all local data" button reachable and functional via controller
- [ ] Support screen log path visible and readable at 1280×800

### I.6 Steam Cloud exclusions

```bash
# In Desktop Mode — Konsole:
cat "$HOME/.local/share/convsim/steam_cloud_settings.json"
for d in data db logs models/llm packs exports cache crashes; do
    echo "$d: $(ls "$HOME/.local/share/convsim/$d/.nosteamcloudpath" 2>/dev/null \
      && echo PRESENT || echo MISSING)"
done
```

- [ ] `steam_cloud_settings.json` contains only `last_model_id`
- [ ] `.nosteamcloudpath` present in all required subdirectories

### I.7 Achievements, stats, and rich presence (if included in build)

> Skip if `get_steam_status` returns `is_steam_enabled: false` (see E.12).

- [ ] Achievement notification appears after a scored session (on-screen toast
  or Steam overlay notification visible from Gaming Mode)
- [ ] Rich presence text visible in the Steam Friends list on another device
- [ ] No outbound HTTP calls outside Steamworks SDK during play

### I.8 Battery impact documentation

Run a 15-minute text session while monitoring battery draw.  Use the Steam Deck
performance overlay (Quick Access → Performance) to observe average wattage.

- [ ] Average battery draw during sustained text inference: ___ W
  (target: < 15 W — see [`docs/linux-steamos-requirements.md §SteamOS`](/play/linux-steamos/))
- [ ] Fan behavior during inference: [ ] Silent / [ ] Intermittent spin / [ ] Sustained
- [ ] Result documented in the beta verification report

### I.9 Steam Deck Verified sign-off requirements

These items are required for Valve to grant the Verified tier (G4-02).

- [ ] All TC-11 steps above show PASS (no FAIL results)
- [ ] On-screen keyboard appeared automatically for every text field
- [ ] No required action hidden behind a mouse-only hover state
- [ ] All text readable at 1280×800 from couch distance without zooming
- [ ] Every interactive element had a visible focus ring during controller navigation
- [ ] Default controller config ([`steam/controller_config.vdf`](https://github.com/outrightmental/ConversationSimulator/blob/main/steam/controller_config.vdf)) loaded automatically
  (confirm via Steam Input overlay)
- [ ] Push-to-talk (R1) does not conflict with Steam overlay (Shift+Tab)
- [ ] App exits cleanly and returns to the Steam library home
- [ ] Battery draw documented (I.8 above)

---

## Part J — Steam beta verification sign-off

Complete this section after Parts E, G, H, and I are all finished for the
release candidate build.  This section gates **G3-06** (private beta sign-off)
and contributes evidence for **G4-02** (Steam Deck Verified).

### J.1 Minimum tester coverage

A minimum of five testers must complete at least one full text session and view
the debrief screen before G3-06 can be declared PASS.  At least one tester must
be on each required platform.

| Platform | Required testers | Status |
|----------|-----------------|--------|
| Windows 10 / 11 (x86-64) | ≥ 2 | TBD |
| macOS — Apple Silicon | ≥ 1 | TBD |
| macOS — Intel | ≥ 1 | TBD |
| Linux (x86-64) | ≥ 1 | TBD |
| Steam Deck (SteamOS 3.x, Gaming Mode) | ≥ 1 | TBD for G4-02 |

### J.2 Platform-specific blocker tracking

Any session-ending bug, data-loss bug, or privacy regression found during Parts
E, G, H, or I must be filed as a GitHub issue with the label `beta-testing`
before the gate can be declared.

Use the label `platform:windows`, `platform:macos`, `platform:linux`, or
`platform:steam-deck` to identify the affected platform.  Child issues should
reference this issue as a blocker.

- [ ] All session-ending, data-loss, and privacy-regression bugs are filed
- [ ] All filed blockers are either closed or have a documented maintainer waiver
  before G3-06 is declared PASS

### J.3 Beta verification report

Produce and file the signed-off beta verification report using the template in
[`docs/STEAM_BETA_VERIFICATION_REPORT.md`](/dev/steam-beta-verification/).  The completed report must be
attached to the release issue before the Stage 3 gate is declared open.

- [ ] [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](/dev/steam-beta-verification/) filled out for this build
- [ ] All four platform sign-offs completed (or PARTIAL with documented waiver)
- [ ] Report attached to the release GitHub issue or linked from the release PR
- [ ] Publishing owner has countersigned the aggregate sign-off section

---

## Smoke log

Fill this in for each manual release smoke run.

```
Release version  : vX.Y.Z-alpha.N
Date             : YYYY-MM-DD
Tester           :
Platform         : macOS 14.x / Ubuntu 22.04.x / Windows 11
CPU              : Apple M2 / Intel Core i7-xxxx / AMD Ryzen xxxx
RAM              : xx GB
VRAM             : xx GB (or "none — CPU only")
Model tested     : Qwen3 4B Q4_K_M / (none — fake runtime only)
Source commit    : <git sha>

Part A (CI)      : PASS / FAIL
Part B result    : PASS / FAIL / PARTIAL
Part C acceptance: PASS / PARTIAL / FAIL

Notes:
  -
  -
```

If Part B or Part C includes any failures, attach the artifact directory
(`$TMPDIR/convsim-release-smoke-*/`) to the release issue before proceeding.

---

## Failure reference

When a subsystem fails, the output labels the failing step:

| Label | Subsystem | Likely cause |
|---|---|---|
| `[setup]` | Monorepo paths | Missing file or directory after checkout |
| `[health]` | Backend | convsim-core not running; database migration failed |
| `[web]` | Frontend | TypeScript error; build tool missing |
| `[model-mgr]` | Model manager | Registry parse error; model download check regression |
| `[scenario-lib]` | Scenario library | Pack import broken; scenario route error |
| `[text-session]` | Session / turn | Turn pipeline error; session state machine regression |
| `[debrief]` | Debrief engine | Scoring logic error; DB query failure |
| `[pack-valid]` | Pack validation | Schema change broke existing packs; YAML parse error |
| `[voice]` | Voice fallback | TTS worker state machine regression; fallback path not taken |
| `[offline]` | Offline policy | Outbound call detected; network guard not active |
| `[packaged-startup]` | Packaged startup | Config resolution broke; dev import leaked into bundle |
| `[e2e-playthrough]` | E2E playthrough | Full playthrough broken in packaged-env mode; official packs not loading |
| `[artifact-inspect]` | Artifact inspection | Version not stamped; icon missing; forbidden file in depot; permission bit wrong |
| `[workbench]` | Creator workbench | Pack import/export or file API broken; workbench route error |
| `[steam-beta]` | Steam beta verification | Platform-specific install, OS trust state, or Steam-client-specific regression; see Parts E / G / H / I |

CI artifacts for failed runs are uploaded to GitHub Actions under the job name
`release-smoke-<platform>` and retained for 7 days.

Steam beta verification failures (Parts E, G, H, I) must be filed as GitHub
issues with the label `beta-testing` and the appropriate `platform:*` label
before the Stage 3 gate (G3-06) can be declared PASS.  See Part J for the
complete sign-off process and [`docs/STEAM_BETA_VERIFICATION_REPORT.md`](/dev/steam-beta-verification/) for the
report template.
