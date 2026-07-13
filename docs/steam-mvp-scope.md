<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam MVP Scope and Release Gates

> **Purpose of this document:** Convert the Steam release roadmap into concrete
> feature lists and pass/fail gates for each release stage. This is the
> "definition of done" companion to
> [STEAM_ROADMAP.md](STEAM_ROADMAP.md) (principles and release train) and
> [publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md)
> (risks and mitigations).

---

## Minimum Steam playable release

A build qualifies as the minimum Steam playable release when **every item below
is present and passing**. These are not stretch goals — they are the floor. A
missing item is a blocker, not a deferral.

### Feature requirements

| # | Feature | Acceptance criterion |
|---|---------|---------------------|
| F-01 | One-click desktop launch | A clean-install player can run the installer, complete first-run setup, and reach the home screen without any CLI steps. No terminal, no `pip install`, no `./scripts/` required. |
| F-02 | First-run model setup | The Model Manager wizard guides the player through selecting and downloading a starter model. All six mandatory disclosure fields (name, source, license, size, SHA-256, destination path) are visible before the Download button is active. |
| F-03 | At least one polished text scenario | At least one scenario from the official packs produces a coherent NPC conversation, state transitions, and a scored debrief within normal latency bounds (≤ 60 s per turn on the reference hardware defined in the release checklist). |
| F-04 | Four official packs | All four official packs — Job Interview Basics, Everyday Negotiation, Language Café, Difficult Conversations — are pre-installed and selectable without additional setup or download. |
| F-05 | Complete debrief loop | Every session can be ended by the player and produces a debrief screen with rubric scores and an export option. A session with zero scored turns must still produce a debrief (not an error). |
| F-06 | Privacy controls | The Settings UI exposes: transcript history view, one-click clear of all saved session history (deleting stored sessions, e.g. via `DELETE /api/sessions/{id}` per session), and a displayed local data-path (`~/.convsim/`). The player must be able to delete all session data without touching the filesystem manually. |
| F-07 | No network requirement during installed play | The offline smoke test passes from the installed app binary (not the source checkout) on all three target platforms. No DNS lookup, TCP connection, or HTTP request occurs during a play session. |

### Features not required for the minimum playable release

The following are **not** required for the minimum Steam playable release. They
are either targeted optional features (see next section) or explicitly
post-launch.

- Voice input (Whisper STT)
- Voice output (Kokoro / sherpa-onnx TTS)
- Steam Cloud sync
- Achievements, stats, or rich presence
- Steam Deck Verified tier
- Community pack browser or in-app pack distribution
- Workbench or creator tools visible to regular players

---

## Optional-but-targeted release features

These features are **targeted** for the public Steam release (Stage 4) but do
not block the minimum playable release gate. If a feature is not ready when the
public release decision is made, it ships as a post-launch update — not as a
hold on the release.

| Feature | Target stage | Notes |
|---------|-------------|-------|
| Local STT — Whisper.cpp voice input | Stage 4 (public release) | Tested in CI via the voice-unavailable fallback path (`test_voice_smoke.py -k fallback`). The full voice path requires the whisper.cpp runtime sidecar. Voice input is opt-in; its absence does not break text mode. |
| Local TTS — Kokoro / sherpa-onnx voice output | Stage 4 (public release) | Same fallback path as STT. TTS is opt-in; its absence does not break text mode. NPC responses still display as text. |
| Steam Cloud sync for non-sensitive settings | Stage 4 (public release) | Sync scope: display preferences, last-used model ID, UI layout state. Transcripts, model weights, audio files, and session history must never sync to Steam Cloud. |
| Steam achievements, stats, and rich presence | Stage 4 (public release) | Achievement progress is tracked locally. Nothing is transmitted unless the player interacts with the Steam overlay. Achievement definitions must not require telemetry or any outbound call during play. |
| Steam Deck Verified tier | Stage 4 (public release) | Verification checklist is in [STEAM_ROADMAP.md — Steam Deck verification checklist](STEAM_ROADMAP.md#steam-deck-verification-checklist). Valve has final say; meeting all checklist items makes approval likely but does not guarantee it. |

---

## Pass/fail release gates

Each release stage has a concrete set of gates. A stage is open only when all
required gates show **PASS**. A gate that cannot be fully automated must have a
named owner and a sign-off date before the stage is declared open.

Automated gates are run by CI on every commit. Manual gates are run by the
platform or content team against a release candidate build.

### Stage 2 gate — Packaged desktop alpha

Entry criterion: GitHub MVP (ROADMAP.md Milestone 1 items all checked off) is
tagged.

| Gate ID | Gate | Method | Pass criterion |
|---------|------|--------|----------------|
| G2-01 | Local-only smoke | CI + manual | `node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic` exits 0 when run from the **installed app directory** (not the source checkout). No outbound TCP connection detected during the scripted session. Verified on all three target platforms (Windows, macOS, Linux). |
| G2-02 | Pack validation | CI | All four official packs pass `convsim validate-pack` with zero errors and zero warnings, using the pack validator binary from the installed app. |
| G2-03 | Structured-output safety | CI | Safety policy unit tests pass (`services/convsim-core/tests/test_safety_policy_service.py`). At least one synthetic adversarial input (content category: `nsfw_sexual_content`) is rejected at the input router before reaching the NPC runtime. Global non-overridable rules (`minors_romantic_or_sexual`, `self_harm_crisis`) cannot be disabled by any pack configuration. |
| G2-04 | Platform packaging | CI + manual | Installer builds successfully on Windows (NSIS), macOS (DMG), and Linux (AppImage or Flatpak). Installer completes on a clean OS image without pre-installing Python, Node.js, or any development dependency. |
| G2-05 | One-click launch | Manual | A tester with no prior knowledge of the project reaches a running text session using only the installer, the Model Manager wizard, and in-app prompts. No documentation, terminal, or file-manager navigation is required. |

### Stage 3 gate — Steam private beta

Entry criterion: Stage 2 gate fully passed and signed off. Steam page draft
approved by Valve for private access.

| Gate ID | Gate | Method | Pass criterion |
|---------|------|--------|----------------|
| G3-01 | Signing and notarization | Manual | macOS DMG is notarised with an Apple Developer ID certificate; Gatekeeper passes on a clean macOS install without any security bypass. Windows installer is code-signed with an EV certificate; SmartScreen does not block installation on a clean Windows install. |
| G3-02 | Steam depot content audit | Manual | Steam depot manifest contains no `.gguf`, `.bin`, or `.safetensors` model-weight files. No model download is triggered during Steam depot installation. Matches checklist item SR-08 in the compliance register. |
| G3-03 | Steam overlay compatibility | Manual (beta testers) | Steam overlay (Shift+Tab) opens and closes without breaking the app or the current session. Push-to-talk key (if voice is enabled) does not conflict with Steam overlay defaults (F12 screenshot, Shift+Tab overlay). |
| G3-04 | Release-blocking risks resolved | Manual | All risks marked `Release-blocking: YES` in [STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) show status `MITIGATED`, `ACCEPTED`, or `DEFERRED`. No release-blocking risk remains `OPEN` or `IN PROGRESS`. |
| G3-05 | Compliance checklists signed off | Manual | All compliance checklist items `SR-01` through `SR-08` in the compliance register are signed off by their named owners with a date. |
| G3-06 | Beta session verification | Manual (beta testers) | A minimum of five testers (at least one on each of Windows, macOS, and Linux) complete a full text session and view the debrief screen. No session-ending bugs, data-loss bugs, or privacy regressions remain open at the time the beta gate is declared. |

### Stage 4 gate — Public paid ($9.99) Steam release

Entry criterion: Stage 3 gate fully passed and Valve private beta approval
received.

| Gate ID | Gate | Method | Pass criterion |
|---------|------|--------|----------------|
| G4-01 | Valve Steam review approval | Valve review | Valve's Steam review team has approved the app for **public** release (not just private beta). The store page is live or scheduled. |
| G4-02 | Steam Deck Verified tier | Valve review | Valve has granted the Verified tier. All items in the [Steam Deck verification checklist](STEAM_ROADMAP.md#steam-deck-verification-checklist) passed during Stage 3 beta testing. |
| G4-03 | Full release checklist | CI + manual | All parts (A, B, C, D) of [docs/release-checklist.md](release-checklist.md) are complete with no unresolved failures. |
| G4-04 | Store page accuracy | Manual | Steam store page is reviewed by the publishing owner: no claims of AI therapy, diagnosis, or legal advice; the base app is listed at its one-time **$9.99** price with no misleading "free" or "free-to-play" claims — the free build-from-source path (GitHub, open source) is disclosed accurately, and the paid Steam package is described as funding development rather than unlocking anything the source build lacks; premium scenario-pack DLC is described accurately as first-party paid content delivered via Steam DLC (Option A), without claiming the DLC content is open source or that it lives in the public repo; local-first and privacy-first copy is accurate and is not undercut by the pricing copy (a price is not a privacy change). |
| G4-05 | Voice smoke (if included) | CI + manual | If STT and/or TTS are included in the release build, voice smoke tests (`services/convsim-core/tests/test_voice_smoke.py`) pass end-to-end on all three target platforms. If voice is not included in the release build, the voice-unavailable fallback path must pass. |

---

## Explicitly post-launch

The following features are **not in scope for any v1 Steam release gate**. They
are listed here to prevent scope creep: none of these items will be considered
for a release-gate waiver or a last-minute inclusion.

A future proposal to build any item in this list requires its own issue,
design document, and acceptance criteria. It must not compromise the
local-first, open-source, and no-telemetry principles of the base project.

| Feature | Why deferred |
|---------|-------------|
| Community content marketplace | Requires payment rails, content moderation infrastructure, and Valve approval for in-app transactions. None of this exists in v1. Tracked in Stage 5 of the release train. |
| Creator revenue sharing | Depends on the marketplace. Cannot exist independently of it. |
| Third-party / creator-sold DLC and in-app microtransactions | First-party premium scenario-pack DLC is **not** deferred: it ships as separate Steam DLC (Option A) with its own Steam App IDs and content depots, authored in the private `ConversationSimulator-DLC` repo and delivered through Steam's DLC storefront (base depots exclude DLC content), so it is simply out of scope for the base-app release gates in this document. What remains post-launch is a *third-party* creator marketplace with in-app payment rails and Valve microtransaction review, which does not exist in v1. First-party DLC content is paid, not open source. |
| Multiplayer or shared sessions | Server infrastructure, latency management, identity, and live moderation are orthogonal to the local-first architecture and would require a fundamentally different backend. |
| VR support | Platform-specific SDKs, a 3D renderer, and dedicated hardware targets are a separate product effort that the current stack does not address. |
| Plugin execution in scenario packs | Executable plugins are explicitly prohibited by the safety policy (`CP-01` in the compliance register) and the pack schema (`scripts` field rejected). Revisiting this requires a sandboxing architecture and a separate security review — it cannot be added incrementally. |

These items are also recorded in [ROADMAP.md — Not now](../ROADMAP.md#not-now)
and in the Stage 5 description of the
[release train](STEAM_ROADMAP.md#release-train).

---

## Roadmap issue set

The following GitHub issues implement the Steam edition roadmap in sequence.
Each issue corresponds to one document or gate in the release preparation.

| Title | Document delivered | Stage dependency |
|-------|-------------------|-----------------|
| [[Steam Roadmap] Add Steam edition roadmap addendum and release principles](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-roadmap-addendum+in%3Atitle) | [docs/STEAM_ROADMAP.md](STEAM_ROADMAP.md) | Stage 1 prerequisite |
| [[Steam Roadmap] Create Steam compliance and risk register for local-AI distribution](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-compliance-risk-register+in%3Atitle) | [publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) | Stage 3 prerequisite |
| [[Steam Roadmap] Define Steam MVP scope and release gates](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-mvp-scope+in%3Atitle) | [docs/steam-mvp-scope.md](steam-mvp-scope.md) | Stage 2 prerequisite |

All open and closed issues in the Steam release work stream:
[GitHub — issues with `[Steam Roadmap]` prefix](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+%5BSteam+Roadmap%5D+in%3Atitle)

---

## Links

- [STEAM_ROADMAP.md](STEAM_ROADMAP.md) — release principles, release train, target platforms, and model download transparency spec
- [publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register and compliance checklists (SR-01 through SR-09)
- [ROADMAP.md](../ROADMAP.md) — base project roadmap and MVP acceptance criteria
- [release-checklist.md](release-checklist.md) — Parts A–D platform smoke matrix
- [acceptance/player-checklist.md](acceptance/player-checklist.md) — player acceptance gate
- [acceptance/creator-checklist.md](acceptance/creator-checklist.md) — creator acceptance gate
- [acceptance/developer-checklist.md](acceptance/developer-checklist.md) — developer acceptance gate
- [GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones) — issue tracking
