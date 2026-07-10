<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# QA Steam Platform Matrix

> **Purpose of this document:** Define the manual and automated test coverage
> required for a credible all-platform Steam release of Conversation Simulator.
> This is the QA companion to [steam-mvp-scope.md](steam-mvp-scope.md) (feature
> gates) and [release-checklist.md](release-checklist.md) (release smoke steps).

---

## 1. Platform and OS matrix

| Platform | OS versions in scope | Architecture | Installer format | Tier |
|----------|---------------------|--------------|------------------|------|
| **Windows** | Windows 10 (build 19041+), Windows 11 | x86-64 | NSIS `.exe`, MSI | Required |
| **macOS — Apple Silicon** | macOS 13 Ventura, macOS 14 Sonoma, macOS 15+ | arm64 | `.dmg` | Required |
| **macOS — Intel** | macOS 13 Ventura, macOS 14 Sonoma | x86-64 | `.dmg` | Required |
| **Linux (glibc)** | Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Fedora 40+ | x86-64 | AppImage, `.deb` | Required |
| **Steam Deck / SteamOS** | SteamOS 3.x (based on Arch Linux) | x86-64 | Flatpak / AppImage | Required for public release |

### OS versions explicitly out of scope for v1

- Windows 8.1 and earlier — no WebView2 support
- macOS 12 Monterey — dropped from QA matrix; may still work but is untested
- 32-bit (x86) on any platform
- ARM Windows — not targeted in v1
- ChromeOS / Android / iOS — not targeted in v1

---

## 2. CPU / GPU / RAM hardware tiers

| Tier | Example hardware | RAM | VRAM | Expected NPC first-token | QA priority |
|------|-----------------|-----|------|--------------------------|-------------|
| **Minimum** | 4-core x86-64 CPU, integrated graphics | 8 GB | 0 GB (CPU only) | 5–15 s | Must pass (gate) |
| **Starter** | 6-core CPU, integrated GPU or low-end discrete | 12 GB | 2–4 GB | 2–6 s | Must pass |
| **Recommended** | Apple M2 / NVIDIA RTX 3060, mid-range CPU | 16 GB | 4–8 GB | 0.5–2 s | Must pass |
| **High-end** | Apple M3 Pro / NVIDIA RTX 4080 | 32 GB+ | 12–24 GB | < 0.5 s | Validation only |

### Model size guidance per tier

| Tier | Recommended model | Notes |
|------|------------------|-------|
| Minimum | 2–3 B Q4 quantised (≤ 2 GB GGUF) | CPU-only; warn if < 8 GB RAM |
| Starter | 4 B Q4_K_M (≈ 2.6 GB GGUF) | Qwen3 4B reference model |
| Recommended | 7–8 B Q4_K_M (≈ 5 GB GGUF) | Full GPU offload recommended |
| High-end | 13 B+ Q4_K_M or larger | Enthusiast / creator use |

### Graceful-degradation expectations

- **Minimum tier:** text-only is the default recommendation; app must surface a visible performance warning when first-token latency exceeds 10 s; STT/TTS disabled by default.
- **Starter tier:** app recommends a 4 B model and CPU+GPU split; performance warning at > 5 s.
- **All tiers:** a turn that times out after 60 s must produce an in-app error with a recovery action; the session must remain open for retry.
- **Out-of-memory:** the app must display a readable error message; it must not crash silently or corrupt the session database.

---

## 3. Steam Deck status

Steam Deck is a **required** platform for the Stage 4 public release. Valve
must grant Verified (not merely Playable) tier before the public release gate
opens.

### Input device coverage

| Input type | Expected behaviour on Steam Deck |
|-----------|----------------------------------|
| D-pad + A/B/X/Y buttons | Navigate menus, confirm / cancel dialogs |
| Left stick | Scroll lists; equivalent to mouse scroll |
| Right trackpad | Pointer control for precise clicks |
| On-screen keyboard | Must appear automatically when any text field is focused |
| Back buttons (L4/R4/L5/R5) | May be left unmapped in v1; must not break play |
| Gyro | Unmapped in v1 |

### Steam Deck verification checklist

Each item must be checked by a tester on physical Steam Deck hardware running
SteamOS 3.x in Gaming Mode before G4-02 can be declared PASS.

| Check | Controller-only test | Result |
|-------|---------------------|--------|
| App launches in Gaming Mode from the Steam library without extra setup. | Use controller to launch from library | [ ] PASS / [ ] FAIL |
| Home, Library, Setup, Conversation, Debrief, Model Manager, Settings, Support, and Workbench are fully navigable with the controller alone. | TC-11 full walkthrough | [ ] PASS / [ ] FAIL |
| Every interactive element has a visible focus ring at 1280×800 from couch distance. | Inspect each screen during TC-11 | [ ] PASS / [ ] FAIL |
| On-screen keyboard appears automatically for every text input field (no manual invocation needed). | TC-11.5 and TC-11.7 | [ ] PASS / [ ] FAIL |
| R1 (right shoulder) triggers push-to-talk in voice mode. | TC-11.6 | [ ] PASS / [ ] FAIL |
| All text is readable at 1280×800 (native resolution) without zooming or horizontal scrolling. | Inspect transcript, meters, debrief | [ ] PASS / [ ] FAIL |
| No required action is hidden behind a mouse-only hover state. | All screens — controller only | [ ] PASS / [ ] FAIL |
| DebugDrawer is excluded from the controller focus ring (dev builds only). | TC-11.11 | [ ] PASS / [ ] N/A |
| Default Steam Input config (`steam/controller_config.vdf`) is loaded automatically. | Launch game; check Steam Input overlay | [ ] PASS / [ ] FAIL |
| Offline smoke test passes under SteamOS 3.x (no outbound network during play). | TC-09 on Steam Deck | [ ] PASS / [ ] FAIL |
| Steam overlay (Shift+Tab) opens and closes without breaking the current session. | TC-11.12 | [ ] PASS / [ ] FAIL |
| Approximate battery impact documented (see §5 performance thresholds). | Observe during TC-11 | [ ] Documented |

---

## 4. Test cases

Each test case below maps to one or more acceptance gate IDs from
[steam-mvp-scope.md](steam-mvp-scope.md) and/or steps in
[release-checklist.md](release-checklist.md). **Automated** means the case is
or should be covered by CI; **Manual** means it requires a human tester on real
hardware.

### TC-01 Fresh install

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 01.1 | Download and run the platform installer on a clean OS image with no prior Conversation Simulator data | Installer completes without requiring Python, Node.js, or any development dependency | Manual |
| 01.2 | On macOS: verify Gatekeeper prompt appears and the app opens via "Open Anyway" | No persistent security exception required after notarisation; notarised build passes without dialog | Manual |
| 01.3 | On Windows: verify SmartScreen prompt; signed build opens without "More info" click | SmartScreen passes for signed EV build | Manual |
| 01.4 | Confirm `~/.convsim/` (macOS/Linux) or `%USERPROFILE%\.convsim\` (Windows) is created on first launch | Directory present; no data written before first-run wizard | Manual |
| 01.5 | Confirm no model weights are present in the Steam depot after install | `find ~/.convsim/models -name "*.gguf"` returns empty | Manual |

### TC-02 First-run model setup

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 02.1 | Launch app with no model installed | Model Manager wizard is shown automatically; home screen is not accessible until a model is selected or skipped | Manual |
| 02.2 | Open model details before downloading | All six mandatory fields visible: model name, source, license, download size, SHA-256 checksum, destination path | Manual |
| 02.3 | Download the starter model (Qwen3 4B Q4_K_M) | Download progress bar shown; SHA-256 verified after download; model status changes to `"loaded"` | Manual |
| 02.4 | Cancel a download mid-transfer | No partial file remains in `~/.convsim/models/`; model status is `"not installed"` | Manual |
| 02.5 | Attempt to download with insufficient disk space | Clear error message shown; no partial file; app remains functional | Manual |
| 02.6 | Model manager unit tests (no download) | `[model-mgr]` CI gate passes | Automated |

### TC-03 Official pack play

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 03.1 | All four official packs present without additional download | Job Interview Basics, Everyday Negotiation, Language Café, Difficult Conversations all appear in the scenario picker | Manual |
| 03.2 | Pack schema validation | `convsim validate-pack` exits 0 for all four packs; zero errors, zero warnings | Automated |
| 03.3 | Start a session in each official pack | NPC opening line delivered within 10 s (fake runtime) / 60 s (real model, CPU minimum tier) | Manual |
| 03.4 | Complete a multi-turn session in Job Interview Basics | At least 3 player turns completed; NPC responds to each; session ends cleanly | Manual |

### TC-04 Text-only fallback

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 04.1 | Start a session with STT and TTS explicitly disabled | Session runs in text-only mode; no audio UI elements active | Manual |
| 04.2 | Start a session when whisper.cpp is not installed | App falls back to text input automatically; status indicator shows STT unavailable | Manual |
| 04.3 | Start a session when Kokoro is not running | NPC responses display as text only; no audio played; no crash | Manual |
| 04.4 | Voice fallback CI tests | `[voice]` gate passes; no `tts_audio_chunk` events in TTS-disabled sessions | Automated |
| 04.5 | Offline smoke test with text-only / fake runtime | `offline-smoke-test` exits 0; no outbound connections | Automated |

### TC-05 STT / TTS where available

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 05.1 | Install whisper.cpp runtime; record a short English phrase; submit via push-to-talk | Non-empty transcript returned; language matches English; NPC responds | Manual |
| 05.2 | Install Kokoro TTS; complete a turn with TTS enabled | At least one `tts_audio_chunk` event; audio plays without distortion | Manual |
| 05.3 | Spanish STT path (Language Café / spanish_coffee) | Transcript returned in Spanish; NPC responds in Spanish | Manual |
| 05.4 | Real-runtime voice smoke tests (`whisper_cpp` + `kokoro` workers) | All stages in `test_voice_smoke.py` pass end-to-end | Automated (CI with runtimes) |
| 05.5 | Push-to-talk key does not conflict with Steam overlay (Shift+Tab) | Both bindings coexist; Steam overlay and push-to-talk both functional | Manual (Steam Deck / desktop) |

### TC-06 Debrief

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 06.1 | End a session after multiple turns and view debrief | Debrief screen loads; rubric scores populated; export option present | Manual |
| 06.2 | End a session with zero scored turns (e.g., immediately after opening line) | Debrief screen loads with empty/zero scores; no crash or error page | Manual |
| 06.3 | Export debrief as JSON | File written to local disk; file contains session metadata, turns, and rubric scores | Manual |
| 06.4 | Debrief engine unit tests | `[debrief]` CI gate passes | Automated |

### TC-07 Privacy controls

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 07.1 | Navigate to Settings and locate privacy controls | Transcript history view, "Clear all local data" button, and local data path (`~/.convsim/`) all visible | Manual |
| 07.2 | Clear all session history via the UI | All sessions deleted from the local SQLite database; no file-manager navigation required | Manual |
| 07.3 | Verify `POST /api/privacy/clear` API | 200 response; sessions table empty afterwards | Automated |
| 07.4 | Disable transcript saving; complete a session | No rows written to `sessions` or `session_events` tables after session ends | Manual |
| 07.5 | Verify no conversation content in log files | `~/.convsim/logs/` contains no raw player text or NPC responses | Manual |
| 07.6 | Confirm `telemetry_enabled` defaults to false in `/api/health` | `privacy.telemetry_enabled` is `false`; no outbound calls during session | Automated |

### TC-08 Logs and crash bundle

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 08.1 | Reproduce a known error (e.g., start session without model) | Error written to `~/.convsim/logs/`; no raw player text in log; log rotation active | Manual |
| 08.2 | Locate log directory via the UI | Settings shows or links to log directory path | Manual |
| 08.3 | Bundle logs for a bug report | User can copy log path and share with support; log contains enough diagnostic context to reproduce | Manual |
| 08.4 | Backend log unit tests | Service startup, session lifecycle, and safety events logged at correct levels; no PII in log output | Automated |

### TC-09 Offline play

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 09.1 | Block all network access (firewall or airplane mode) and start a play session | Session runs normally with a locally installed model; no error or network-related warning | Manual |
| 09.2 | Offline smoke test (scripted, from installed app binary) | `offline-smoke-test` exits 0 from the installed app directory (not source checkout) | Manual + Automated |
| 09.3 | Network policy unit tests | `[offline]` CI gate passes; `NetworkBlockedError` raised for any out-of-band connection attempt during play | Automated |
| 09.4 | Confirm no background ping at startup | Packet capture or system proxy shows zero outbound HTTP/HTTPS requests on app launch | Manual |

### TC-10 Uninstall and reinstall

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 10.1 | Uninstall the app using the platform mechanism (Windows Add/Remove Programs, macOS drag to Trash, Linux AppImage delete) | App binary and assets removed; `~/.convsim/` data directory **not** removed by default | Manual |
| 10.2 | Reinstall after uninstall with existing data directory | App launches; existing sessions and model files detected; no re-download required | Manual |
| 10.3 | "Clear all local data" then reinstall | First-run wizard appears; model download required; no stale state from previous install | Manual |
| 10.4 | Reinstall over an existing install (upgrade path) | Existing sessions preserved; no database migration error; model files intact | Manual |

### TC-11 Controller-only full session (Steam Deck Verified gate)

Full end-to-end play from launch to quit using the controller alone — no
keyboard or mouse contact.  All steps must be completable with D-pad, A/B/X/Y
buttons, left stick, and the on-screen keyboard only.  Corresponds to the
controller-only column added to §3 (Steam Deck verification checklist).

| # | Step | Pass criterion | Method |
|---|------|----------------|--------|
| 11.1 | Launch app in Gaming Mode from Steam library | App reaches Home screen; focus is placed on the first interactive element | Manual — Steam Deck hardware |
| 11.2 | Navigate Home screen with D-pad / left stick | Every link and status badge reachable; a visible focus ring appears on each element at 1280×800 from couch distance | Manual — Steam Deck hardware |
| 11.3 | Navigate to Scenario Library via controller | Focus moves correctly through nav links; Scenarios screen loads | Manual |
| 11.4 | Select a scenario pack and choose a scenario | Card selection works; Setup screen reached with no keyboard/mouse | Manual |
| 11.5 | Enter a player name or adjust setup field with on-screen keyboard | Steam floating keyboard appears automatically on text field focus; dismissed on confirm | Manual |
| 11.6 | Start a conversation session in voice mode | Session launches; R1 (right shoulder) triggers push-to-talk; NPC responds | Manual |
| 11.7 | Submit at least one text turn using the on-screen keyboard | On-screen keyboard appears on input focus; text submitted; NPC responds | Manual |
| 11.8 | End the session and navigate to the Debrief screen | End session button reachable via controller; Debrief loads | Manual |
| 11.9 | Navigate Debrief screen and confirm readability | All debrief scores and text readable at 1280×800; no clipped controls | Manual |
| 11.10 | Navigate to Model Manager, Settings, Support, and Workbench screens | Each screen fully navigable; no interactive element requires mouse hover | Manual |
| 11.11 | Confirm DebugDrawer is excluded from controller focus ring | DebugDrawer (dev-mode only) never receives focus during D-pad navigation | Manual — dev build only |
| 11.12 | Open and close Steam overlay (Shift+Tab) during a session | Overlay opens and closes; controller focus resumes correctly in the app | Manual |
| 11.13 | Quit the app via controller | App closes cleanly; no orphaned processes | Manual |

---

## 5. Performance thresholds

These thresholds are **pass/fail** criteria for QA sign-off. A platform + tier combination that cannot meet the minimum threshold is a blocker, not a deferral.

| Metric | Minimum tier threshold | Starter tier threshold | Recommended tier threshold | Notes |
|--------|----------------------|----------------------|--------------------------|-------|
| Session start (first NPC line) | ≤ 60 s | ≤ 20 s | ≤ 5 s | Timed from "Start session" button press |
| First token latency | ≤ 15 s | ≤ 5 s | ≤ 2 s | From player turn submission to first streamed token |
| Full NPC response | ≤ 90 s | ≤ 30 s | ≤ 10 s | From player turn to complete response |
| Debrief generation | ≤ 30 s | ≤ 15 s | ≤ 5 s | From "End session" to debrief screen ready |
| App cold-start to home screen | ≤ 10 s | ≤ 5 s | ≤ 3 s | Model not counted; model load is separate |
| Model load (first load after download) | ≤ 120 s | ≤ 60 s | ≤ 20 s | One-time; subsequent loads may be faster via cache |

### Steam Deck–specific targets

| Metric | Target |
|--------|--------|
| Battery impact during text session | < 15 W average (document measured draw) |
| First-token latency on Steam Deck (Starter tier, 4 B model) | ≤ 30 s |
| Fan spin-up during sustained inference | Document observed; acceptable if intermittent |

### Graceful-degradation expectations

- When first-token latency exceeds the threshold for the detected tier, the app must surface an in-app performance tip linking to Runtime Settings.
- When RAM is insufficient for the selected model, the app must reject the model load with a clear "Insufficient memory" message before any OOM condition occurs.
- When VRAM is insufficient for full GPU offload, the app must fall back to CPU+GPU split or CPU-only mode automatically and inform the player.
- All degradation messages must be actionable (link to settings or model manager) and must not expose a stack trace to the player.

---

## 6. Private beta tester and machine inventory

A minimum of five testers covering the required platforms must complete at
least one full text session before the Stage 3 gate (G3-06) can be declared
PASS.

### Target coverage

| Platform | Required testers | Preferred hardware examples | Status |
|----------|-----------------|----------------------------|--------|
| Windows 10 / 11 (x86-64) | ≥ 2 | Mid-range gaming laptop (RTX 3060), budget office desktop (integrated GPU) | TBD |
| macOS — Apple Silicon | ≥ 1 | MacBook Air M2 / Mac Mini M2 | TBD |
| macOS — Intel | ≥ 1 | MacBook Pro Intel (2019–2020) | TBD |
| Linux (x86-64) | ≥ 1 | Ubuntu 22.04 desktop or VM; Fedora 40 | TBD |
| Steam Deck | ≥ 1 | Physical Steam Deck (OLED preferred) running SteamOS 3.x in Gaming Mode | TBD |

### Beta tester sign-up process (placeholder)

1. Tester receives a Steam private beta key from the Outright Mental publishing account.
2. Tester installs the app from the Steam library and completes the first-run model setup.
3. Tester completes the session verification steps in TC-03 and TC-06 and files the result in the beta feedback form (link TBD).
4. Maintainer reviews results; any session-ending, data-loss, or privacy-regression bug blocks the Stage 3 gate.

> **Note:** Machine and tester assignments will be updated in this table when
> the Stage 3 beta programme launches. If you are an Outright Mental team member
> with access to a listed platform, open a GitHub issue with the label
> `beta-testing` to register.

---

## 7. QA sign-off template

Copy this template and fill it in for each platform before declaring the
corresponding release gate PASS. One completed sign-off is required per
platform per gate stage.

```
=== Conversation Simulator — QA Sign-Off ===

Gate stage       : [ ] Stage 2 (packaged alpha)  [ ] Stage 3 (Steam beta)  [ ] Stage 4 (public release)
Platform         : ___________________________________  (e.g. Windows 11 x86-64)
Build version    : vX.Y.Z-alpha.N  (or Steam build ID)
Build date       : YYYY-MM-DD
Tester name      :
Tester email     :
Sign-off date    :

--- Hardware ---
CPU              : ___________________________________
RAM              : ___ GB
GPU / VRAM       : ___________________________________ / ___ GB  (or "integrated" or "CPU only")
Model tested     : ___________________________________ (e.g. Qwen3 4B Q4_K_M)
Hardware tier    : [ ] Minimum  [ ] Starter  [ ] Recommended  [ ] High-end

--- Automated gates (CI) ---
Part A CI gates  : [ ] PASS  [ ] FAIL  (link to CI run: ___________________________)

--- Manual test results ---
TC-01 Fresh install           : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-02 First-run model setup   : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-03 Official pack play      : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-04 Text-only fallback      : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-05 STT/TTS (if included)   : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-06 Debrief                 : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-07 Privacy controls        : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-08 Logs and crash bundle   : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-09 Offline play            : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________
TC-10 Uninstall / reinstall   : [ ] PASS  [ ] FAIL  [ ] SKIP  Notes: __________________

--- Performance ---
Session start latency    : ___ s  [ ] Within threshold  [ ] Exceeds threshold
First-token latency      : ___ s  [ ] Within threshold  [ ] Exceeds threshold
Full NPC response        : ___ s  [ ] Within threshold  [ ] Exceeds threshold

--- Steam Deck only ---
Controller navigation    : [ ] PASS  [ ] FAIL  [ ] N/A
On-screen keyboard       : [ ] PASS  [ ] FAIL  [ ] N/A
Offline smoke (SteamOS)  : [ ] PASS  [ ] FAIL  [ ] N/A
Battery draw (observed)  : ___ W average  [ ] N/A

--- Overall result ---
[ ] PASS — all required test cases passed; no blocking issues found
[ ] PARTIAL — failures noted; see issues listed below; requires maintainer waiver
[ ] FAIL — one or more blocking issues remain open

Open blocking issues (GitHub #):
  -
  -

Additional notes:
  -
  -

Signed: ___________________________ (tester)
Countersigned: ___________________________ (maintainer, if PARTIAL or for Stage 4)
```

### Aggregate beta verification report

After all per-platform sign-offs above are complete, combine them into the
aggregate beta verification report using the template in
[`docs/STEAM_BETA_VERIFICATION_REPORT.md`](STEAM_BETA_VERIFICATION_REPORT.md).
The completed report must be attached to the release GitHub issue before the
Stage 3 gate (G3-06) can be declared PASS.

### Steam review sign-off (Stage 4 public release)

Before opening the Stage 4 gate, the publishing owner must complete the
following Valve-facing sign-off in addition to the platform QA sign-offs above.

- [ ] All platform QA sign-offs (§7 above) are filed and show PASS for Windows, macOS Apple Silicon, macOS Intel, Linux, and Steam Deck.
- [ ] Valve has approved the store page for public release (G4-01).
- [ ] Valve has granted the Steam Deck Verified tier (G4-02).
- [ ] Steam depot content audit (G3-02) confirmed: no model weights in depot.
- [ ] Store page reviewed: no claims of AI therapy, diagnosis, or legal advice; local-first copy accurate (G4-04).
- [ ] All compliance checklist items SR-01 through SR-08 signed off (G3-05).
- [ ] Release-blocking risks in STEAM_COMPLIANCE_AND_RISK_REGISTER.md show MITIGATED, ACCEPTED, or DEFERRED (G3-04).

```
Steam review sign-off
Publishing owner : ___________________________
Date             : YYYY-MM-DD
Steam App ID     : ___________________________
Build submitted  : ___________________________
Notes            :
  -
```

---

## 8. Links

- [steam-mvp-scope.md](steam-mvp-scope.md) — feature requirements and pass/fail gates (G2–G4)
- [STEAM_ROADMAP.md](STEAM_ROADMAP.md) — release principles, release train, Steam Deck verification checklist
- [STEAM_BETA_VERIFICATION_REPORT.md](STEAM_BETA_VERIFICATION_REPORT.md) — aggregate signed-off beta verification report template (all four platforms)
- [release-checklist.md](release-checklist.md) — Parts A–D platform smoke matrix; Parts E (Windows), G (macOS), H (Linux/SteamOS), I (Steam Deck), J (sign-off) for Steam beta verification
- [performance.md](performance.md) — hardware tier definitions and latency guidance
- [platform-notes.md](platform-notes.md) — platform-specific build and install details
- [linux-steamos-requirements.md](linux-steamos-requirements.md) — glibc requirements, SteamOS hardware profile, AppImage behavior
- [privacy.md](privacy.md) — local-first promise and data handling
- [network-security.md](network-security.md) — runtime network enforcement
- [voice-smoke-tests.md](voice-smoke-tests.md) — STT/TTS smoke test procedures
- [publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — compliance checklists and risk register
