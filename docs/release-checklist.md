<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Release checklist

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
> acceptance checklist under `docs/acceptance/` shows PASS (or a documented,
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
- [ ] `[web]` — Web frontend typecheck passes

If any CI gate is red, **do not proceed to Part B** — fix the failure first.

---

## Part B — Manual release smoke

Run this on a **clean profile** (fresh `~/.convsim/` directory or a new user
account) to catch first-run issues that don't appear on development machines.

### Minimum hardware for real-model smoke

| Item | Minimum | Recommended |
|---|---|---|
| OS | macOS 12, Ubuntu 22.04, Windows 10 build 19041 | Latest stable |
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
| `[workbench]` | Creator workbench | Pack import/export or file API broken; workbench route error |

CI artifacts for failed runs are uploaded to GitHub Actions under the job name
`release-smoke-<platform>` and retained for 7 days.
