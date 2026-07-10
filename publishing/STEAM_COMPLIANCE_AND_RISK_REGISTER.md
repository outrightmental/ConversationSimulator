<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Compliance and Risk Register

> **Purpose:** Capture every compliance, safety, privacy, licensing, and
> platform risk that can block a local-AI Steam release. Each risk has an owner,
> a mitigation, a release-blocking status, and a current disposition. Update
> this register whenever a risk changes state.
>
> **Scope:** Steam edition of Conversation Simulator — a free, local-first,
> Outright Mental-sponsored title. All risks must be resolved or formally
> accepted before the private beta gate opens (Stage 3 of the
> [release train](../docs/STEAM_ROADMAP.md#release-train)).

---

## How to read this register

| Column | Meaning |
|--------|---------|
| **ID** | Stable identifier — never reuse a retired ID. |
| **Area** | Risk domain (Privacy, Licensing, Platform, Safety, Content). |
| **Risk** | What could go wrong or block release. |
| **Owner** | Team or individual accountable for mitigation. |
| **Mitigation** | Controls already in place or planned. |
| **Release-blocking** | `YES` — must be resolved before private beta. `NO` — can ship with open risk. `DEFERRED` — intentionally deferred to a post-launch milestone. |
| **Status** | `OPEN`, `IN PROGRESS`, `MITIGATED`, `ACCEPTED`, `DEFERRED`, or `CLOSED`. |

---

## Privacy risks

### PR-01 — Conversation data leaving the player's machine

| | |
|---|---|
| **Area** | Privacy |
| **Risk** | A regression in the network policy layer causes conversation text, prompts, or transcripts to be transmitted to an external server during play. |
| **Owner** | Platform team |
| **Mitigation** | `convsim_core.network_policy.require_network(NetworkMode.PLAY)` blocks all outbound play-mode connections. Offline smoke test (`packages/convsim-cli/tests/offline-smoke-test.test.ts`) installs a socket-level guard and fails CI on any violation. Network policy unit tests run on every commit (`services/convsim-core/tests/test_network_policy.py`). All services bind to `127.0.0.1` — see `docs/network-security.md`. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### PR-02 — Microphone audio persisted without player consent

| | |
|---|---|
| **Area** | Privacy |
| **Risk** | Raw microphone audio is written to disk or transmitted, creating a privacy violation and potential GDPR/CCPA exposure. |
| **Owner** | Platform team |
| **Mitigation** | Raw audio is processed in memory by the local Whisper runtime; only transcribed text is passed to the scenario engine. Audio is never written to disk in the default configuration. The `convsim.privacy.saveRawAudio` developer setting (Settings UI) is `false` by default; when enabled it writes audio to a local temporary directory for debugging only and never transmits it. A pre-release check must confirm it defaults to `false` (see SR-02). See `docs/privacy.md` — Raw audio section. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### PR-03 — Crash bundles containing conversation content

| | |
|---|---|
| **Area** | Privacy |
| **Risk** | An automatic crash reporter (Sentry, Bugsnag, or equivalent) captures a memory dump or log that includes conversation text or player audio, then transmits it to a third-party server. |
| **Owner** | Platform team |
| **Mitigation** | No crash reporting service is integrated in the MVP. Crash output is written to the local log at `~/.convsim/logs/` only. The MVP ships no telemetry subsystem. If crash reporting is ever added, it must be opt-in, must never include conversation content, and must be documented before release. See `docs/privacy.md` — Crash reports section. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### PR-04 — Transcript database accessible to other apps or users

| | |
|---|---|
| **Area** | Privacy |
| **Risk** | The SQLite transcript database at `~/.convsim/db/sessions.db` has file permissions that allow other OS users or processes to read conversation history. |
| **Owner** | Platform team |
| **Mitigation** | The database is created in the user's home directory with OS-default permissions (typically `0600` on POSIX). A pre-release check must verify permissions on each target platform. The `POST /api/privacy/clear` endpoint and Settings UI give players a one-click delete path. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### PR-05 — TTS cache leaking NPC voice content across player accounts

| | |
|---|---|
| **Area** | Privacy |
| **Risk** | On a shared machine, a second OS user accesses the TTS cache at `~/.convsim/tts-cache/` and infers conversation topics from cached phrase audio. |
| **Owner** | Platform team |
| **Mitigation** | Cache lives under the authenticated user's home directory. The TTS cache contains synthesized NPC phrases only — it does not contain player voice or personally identifying information. Shared-machine risk is low given the cache content. Document this limitation in `docs/privacy.md` before beta. |
| **Release-blocking** | NO |
| **Status** | OPEN |

---

## Microphone and audio handling risks

### AU-01 — Microphone permission prompt rejected or silently denied

| | |
|---|---|
| **Area** | Privacy / Platform |
| **Risk** | On macOS and Windows, the OS microphone permission prompt is dismissed or denied, and the app crashes or enters a broken state instead of gracefully falling back to text-only mode. |
| **Owner** | Platform team |
| **Mitigation** | Voice fallback path is tested in CI (`services/convsim-core/tests/test_voice_smoke.py -k fallback`). App must detect STT unavailability and offer text-only mode without error. Tested in Part B.10 of the release checklist. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### AU-02 — Steam overlay capturing microphone push-to-talk

| | |
|---|---|
| **Area** | Platform |
| **Risk** | The Steam overlay's voice chat hotkeys conflict with the app's push-to-talk key, causing unintended Steam broadcast of player audio. |
| **Owner** | Platform team |
| **Mitigation** | Push-to-talk key must be configurable. Default key should not conflict with Steam overlay defaults (F12 screenshot, Shift+Tab overlay). Validate during Steam private beta (Stage 3). |
| **Release-blocking** | YES |
| **Status** | OPEN |

### AU-03 — Audio hardware unavailable on Steam Deck

| | |
|---|---|
| **Area** | Platform |
| **Risk** | Steam Deck in Gaming Mode does not present a microphone by default; the app requires audio input and fails to start a session. |
| **Owner** | Platform team |
| **Mitigation** | Text-only fallback (AU-01 mitigation) covers this case. App must function fully as a text session without audio hardware. Document Steam Deck audio attachment options in the Steam store page. |
| **Release-blocking** | YES |
| **Status** | OPEN |

---

## Model download risks

### MD-01 — Silent model download without player knowledge

| | |
|---|---|
| **Area** | Privacy / Platform |
| **Risk** | A model download is triggered by app startup, an installer script, or a background update check without the player's explicit consent, consuming bandwidth and disk space without warning. |
| **Owner** | Platform team |
| **Mitigation** | The model manager requires explicit player confirmation before any download. Model name, source, license, size, SHA-256 checksum, and destination path must all be displayed before the Download button activates. Silent downloads are explicitly prohibited — see `docs/model-download-policy.md` — Download rules and `docs/STEAM_ROADMAP.md` — Model download transparency. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### MD-02 — Model checksum verification failure leaves a corrupt file

| | |
|---|---|
| **Area** | Safety / Privacy |
| **Risk** | A failed or interrupted download leaves a partial model file at `~/.convsim/models/` that passes a future checksum check (collision or truncation) and causes unpredictable inference behaviour. |
| **Owner** | Platform team |
| **Mitigation** | After transfer, the model manager computes SHA-256 locally and compares against the model registry. On mismatch, the partial file is deleted and an error is shown. The model registry (`model-registry/`) is the authoritative checksum source. No new model entry may be merged without a verified checksum. See `docs/model-download-policy.md` — Checksum policy and retry/resume behaviour for the full specification. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### MD-03 — Model license not surfaced before download

| | |
|---|---|
| **Area** | Licensing |
| **Risk** | A player downloads a model under a non-commercial or attribution-required license (e.g. Llama Community License) without being shown the license terms, creating a compliance gap. |
| **Owner** | Platform team / Content team |
| **Mitigation** | The download confirmation panel must display all six mandatory disclosure fields (model name, source URL, license with link to full text, download size, SHA-256 checksum, destination path) before the player confirms. The `license` and `license_url` fields are required in the model registry schema (`schemas/model-registry.schema.json`). The full disclosure specification is in `docs/model-download-policy.md` — Licence disclosure. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### MD-04 — Bundled model weights in the Steam installer

| | |
|---|---|
| **Area** | Licensing / Distribution |
| **Risk** | A CI or packaging step accidentally bundles model weight files in the Steam depot, violating model license terms that prohibit redistribution via third-party storefronts or adding gigabytes of weight to the installer. |
| **Owner** | Platform team |
| **Mitigation** | Enforced at three layers: (1) SteamPipe `FileExclusion` patterns in all three platform depot VDFs (`steam/depot_*.vdf.tpl`) exclude `*.gguf`, `*.bin`, `*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`; (2) `scripts/depot-audit.sh` / `depot-audit.ps1` scan for weight files, unapproved binary payloads (large pickle/NumPy/ONNX files), dev artefacts, secrets, and test fixtures — the script exits 1 on any violation; (3) the `steam-deploy.yml` workflow runs `scripts/depot-audit.sh` against each platform's staged `steam-content/` directory before steamcmd is invoked, so CI enforces the same weight and unapproved-binary categories as the manual SR-08 checklist. Depot contents are formally documented in `publishing/STEAM_DEPOT_CONTENTS.md`, which also lists the approved binary payload list. Model download rules (no bundling) are defined in `docs/model-download-policy.md`. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

---

## Content-pack safety risks

### CP-01 — Executable code in community scenario packs

| | |
|---|---|
| **Area** | Safety |
| **Risk** | A malicious community pack includes a `scripts` field or an embedded executable that runs on the player's machine at load time or during a session. |
| **Owner** | Platform team / Content team |
| **Mitigation** | Pack schema (`schemas/pack.schema.json`) explicitly rejects any manifest declaring a `scripts` field. Packs are declarative YAML/JSON — no evaluated expressions, no network calls. The pack validator (`convsim validate-pack`) runs at load time and rejects non-conforming packs. See `docs/safety-policy.md` — Pack sandboxing. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### CP-02 — Pack references external URLs for assets

| | |
|---|---|
| **Area** | Privacy / Safety |
| **Risk** | A pack references an external URL for an asset (image, audio), causing an outbound connection during play that violates the local-first promise. |
| **Owner** | Content team |
| **Mitigation** | `allow_external_urls` must be `false` in all packs; the validator rejects `true`. Assets must be within the pack directory. The offline smoke test also catches any outbound connection this would trigger. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### CP-03 — NSFW content in community packs distributed via Steam

| | |
|---|---|
| **Area** | Safety / Platform |
| **Risk** | A community pack containing NSFW content is loaded into the app by a player, violating Steam content policies for a title not registered as Adult Only. |
| **Owner** | Content team |
| **Mitigation** | The safety policy layer enforces `nsfw_sexual_content: stop` globally. Community packs are validated at load time; packs that attempt to disable or weaken global non-overridable rules are rejected. The MVP ships no in-app community pack browser — packs must be installed manually, limiting distribution surface. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

### CP-04 — Prompt injection via pack persona

| | |
|---|---|
| **Area** | Safety |
| **Risk** | A crafted NPC persona contains embedded instructions that override the safety policy layer and cause the model to produce prohibited output. |
| **Owner** | Platform team |
| **Mitigation** | The safety policy system prompt is injected after the NPC persona (later instructions take precedence). The output validator rejects non-conforming `TurnOutput` responses. The input router applies safety matching before calling the NPC runtime. Persona YAML does not support template evaluation or computed expressions. See `docs/safety-policy.md` — Pack sandboxing and prompt injection. |
| **Release-blocking** | YES |
| **Status** | MITIGATED |

---

## MVP content boundaries

The following content categories are **confirmed prohibited** in all MVP packs.
These are not risks to be mitigated — they are firm product decisions that must
remain encoded in the safety policy schema and validator. This section documents
the decisions for Steam review and partner portal audit purposes.

| Content category | Status | Enforcement |
|-----------------|--------|-------------|
| NSFW sexual content | **Prohibited** | Safety policy `nsfw_sexual_content: stop` (configurable, but global non-overridable rules always apply) |
| Romantic or sexual content involving minors | **Prohibited — absolute** | Global non-overridable rule; cannot be disabled by any pack |
| Real-person impersonation | **Prohibited** | `real_person_impersonation` category; pack validator checks NPC names and bios |
| Voice cloning or voice deepfaking | **Prohibited** | `voice_cloning_request` category; blocked at input router before NPC runtime |
| Therapy, diagnosis, or mental-health positioning | **Prohibited** | `medical_or_therapy_claim` category; NPC may *play* a professional in a practice context but must not claim real clinical authority |
| Medical diagnosis or prescription | **Prohibited** | Same as above |
| Professional legal advice | **Prohibited** | `legal_claim` category; same framing rule as therapy |
| Instructional criminal content | **Prohibited** | `criminal_instruction` category; always present with at least `refuse` action |
| Executable scenario-pack plugins | **Prohibited** | Pack schema rejects `scripts` field; packs are declarative data only |
| Self-harm crisis content without resource messaging | **Prohibited — absolute** | `self_harm_crisis: stop_with_resource_message`; global non-overridable |

---

## Licensing risks

### LI-01 — Open-source component license incompatibility

| | |
|---|---|
| **Area** | Licensing |
| **Risk** | A dependency pulled in by the Tauri desktop build or a runtime sidecar carries a copyleft license (GPL, AGPL) that is incompatible with Steam distribution as a compiled binary. |
| **Owner** | Platform team |
| **Mitigation** | Run a full dependency license audit (e.g. `license-checker`, `cargo-deny`) before the private beta depot submission. Identify any GPL/AGPL dependencies and either replace them with permissively licensed alternatives or confirm dynamic linking satisfies the license obligations. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### LI-02 — CC-licensed documentation bundled in the Steam depot

| | |
|---|---|
| **Area** | Licensing |
| **Risk** | Markdown documentation files (SPDX: CC-BY-4.0) are included in the Steam depot and their attribution requirements are not met in the store page or credits screen. |
| **Owner** | Platform team |
| **Mitigation** | Ensure the Steam store page and in-app credits list all required attributions. Documentation files may be excluded from the Steam depot if they are only developer-facing; player-facing docs bundled in the app must carry correct attribution. |
| **Release-blocking** | NO |
| **Status** | OPEN |

### LI-03 — Whisper.cpp and Kokoro runtime licensing

| | |
|---|---|
| **Area** | Licensing |
| **Risk** | Whisper.cpp (MIT) and Kokoro TTS (Apache 2.0) sidecars are bundled in the Steam installer without surfacing their licenses in the credits or NOTICES file. |
| **Owner** | Platform team |
| **Mitigation** | Include license text for all bundled runtimes in the `NOTICE` file at repo root and ensure it is packaged with the installer. Verify runtime licenses before depot submission. |
| **Release-blocking** | YES |
| **Status** | OPEN |

---

## Steam platform risks

### SP-01 — Valve review rejection for local AI content

| | |
|---|---|
| **Area** | Platform |
| **Risk** | Valve's Steam partner review team rejects the app because local AI inference or the nature of the practice scenarios is classified as restricted content under the Steam Distribution Agreement. |
| **Owner** | Outright Mental (publishing) |
| **Mitigation** | Submit for Valve review with clear store page copy explaining the educational practice tool context, the local-first AI model, and the no-NSFW content policy. Engage with Valve's developer support channel before submitting the full review build. Monitor Valve policy updates for AI-generated content. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### SP-02 — Steam Deck verification rejection

| | |
|---|---|
| **Area** | Platform |
| **Risk** | Valve denies Verified tier for Steam Deck due to a controller navigation gap, unreadable text, or missing on-screen keyboard integration, delaying the public release gate. |
| **Owner** | Platform team |
| **Mitigation** | Complete all Steam Deck verification checklist items in `docs/STEAM_ROADMAP.md` — Steam Deck verification checklist before submitting for Valve review. Prioritise controller navigation and on-screen keyboard testing during private beta (Stage 3). |
| **Release-blocking** | YES |
| **Status** | OPEN |

### SP-03 — Steam age-gating required for dating-confidence content

| | |
|---|---|
| **Area** | Platform |
| **Risk** | Valve requires the store page to be age-gated (18+) due to the PG-13 dating-confidence pack content, reducing the title's discoverability and download count. |
| **Owner** | Outright Mental (publishing) |
| **Mitigation** | Dating-confidence scenarios are capped at PG-13 (social, conversational, no sexual content). Confirm with Valve that PG-13 social practice content does not trigger their 18+ age gate. Position the store page clearly as a conversation practice tool. If age-gating is required, accept it rather than weakening content policies. |
| **Release-blocking** | NO |
| **Status** | OPEN |

### SP-04 — Code signing failure on macOS or Windows

| | |
|---|---|
| **Area** | Platform |
| **Risk** | The release build is not code-signed or notarised, causing macOS Gatekeeper or Windows SmartScreen to block installation and generating player support load. |
| **Owner** | Platform team |
| **Mitigation** | macOS: Gatekeeper notarisation is a hard requirement before public release (Stage 4). Windows: SmartScreen Extended Validation code signing is required. Both are tracked as release gates in `docs/STEAM_ROADMAP.md`. Certificates and signing infrastructure must be in place before the private beta depot is built. |
| **Release-blocking** | YES |
| **Status** | OPEN |

### SP-05 — Steam Wallet and future paid DLC path

| | |
|---|---|
| **Area** | Platform / Licensing |
| **Risk** | A future community pack browser or paid DLC path requires Steam Wallet integration, which requires Valve's approval for microtransaction-enabled titles and may trigger additional content review obligations. |
| **Owner** | Outright Mental (publishing) |
| **Mitigation** | The v1 Steam release ships with no payment rails, no premium pack tier, and no microtransactions. Any paid marketplace or DLC content path is explicitly deferred to Stage 5 (post-launch exploration) of the release train. If a paid path is ever pursued, it must go through a separate Valve review, a Steam Wallet integration audit, and a legal review of revenue-sharing obligations before implementation. |
| **Release-blocking** | NO (deferred) |
| **Status** | DEFERRED |

---

## Release checklist for QA

This checklist is a compliance-specific supplement to the main release checklist
at `docs/release-checklist.md`. Complete both before opening the private beta
gate (Stage 3) or the public release gate (Stage 4).

### SR-01 — Offline smoke test passes

- [ ] `node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic` exits 0.
- [ ] No outbound TCP connection detected during a scripted play session.
- [ ] Verified on all three target platforms (Windows, macOS, Linux).

### SR-02 — Privacy data boundaries verified

- [ ] Transcript database (`sessions.db`) is created with user-only permissions (`0600` on POSIX, restricted ACL on Windows).
- [ ] Raw audio is not written to disk in a default production build (confirm `saveRawAudio` flag is absent or `false`).
- [ ] No crash reporter SDK is present in the production build (grep for Sentry, Bugsnag, Rollbar, Datadog, or equivalent).
- [ ] Telemetry flag is `false` and no telemetry calls are present in the production build.

### SR-03 — Microphone handling

- [ ] App starts and reaches home screen without requesting microphone access.
- [ ] Microphone permission is requested only when a voice-enabled session is started.
- [ ] Denying the microphone permission results in a text-only mode offer, not a crash or broken state.
- [ ] Push-to-talk key does not conflict with Steam overlay defaults.

### SR-04 — Model download transparency

- [ ] No model download is triggered by app startup or background processes.
- [ ] Download confirmation panel displays: model name, source, license, file size, SHA-256 checksum, and destination path — all six fields.
- [ ] License text link opens the correct upstream license URL.
- [ ] Checksum is verified after download; a mismatched file is deleted and an error is shown.
- [ ] No model weight files are present in the Steam depot content.

### SR-05 — Content policy enforcement

- [ ] Pack validator rejects any pack declaring a `scripts` field.
- [ ] Pack validator rejects any pack setting `allow_external_urls: true`.
- [ ] Safety policy blocks `nsfw_sexual_content` at the input router level (can be tested with a synthetic input).
- [ ] Global non-overridable rules (`minors_romantic_or_sexual`, `self_harm_crisis`) cannot be weakened by any pack policy.
- [ ] All four official packs pass `convsim validate-pack` with no warnings.

### SR-06 — Licensing audit

- [ ] Dependency license audit completed; no GPL/AGPL components in the Steam binary without legal sign-off.
- [ ] Whisper.cpp MIT license and Kokoro Apache 2.0 license are present in the installer `NOTICE` file.
- [ ] All bundled model licenses are shown in the in-app model manager and in the `NOTICE` file.
- [ ] No model weight files violating distribution restrictions are included in the installer.

### SR-07 — Steam platform requirements

- [ ] macOS build is notarised with Apple Developer ID; Gatekeeper passes on a clean macOS install.
- [ ] Windows build is code-signed; SmartScreen does not block installation on a clean Windows install.
- [ ] Steam Deck verification checklist in `docs/STEAM_ROADMAP.md` is complete and all items pass.
- [ ] Steam store page copy has been reviewed using the checklist in [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — Store page review checklist.
- [ ] Store page copy accuracy: no language claims AI therapy, diagnosis, or legal advice (gate G4-04).
- [ ] Steam store page does not imply paid content or a marketplace that does not exist in v1 (gate G4-04).
- [ ] All store page copy sign-off rows in [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — Sign-off table are completed with reviewer name and date.
- [ ] All capsule assets, screenshots, and trailer reviewed against the production brief in [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) and uploaded to Steamworks.

### SR-08 — Depot content audit

Run `scripts/depot-audit.sh <depot-dir>` against all three platform depot
content directories before invoking steamcmd. The script must exit 0 on all
three platforms. See `publishing/STEAM_DEPOT_CONTENTS.md` for the authoritative
list of what is allowed and forbidden in each depot.

- [ ] `./scripts/depot-audit.sh steam-content/windows` exits 0 — no violations.
- [ ] `./scripts/depot-audit.sh steam-content/macos` exits 0 — no violations.
- [ ] `./scripts/depot-audit.sh steam-content/linux` exits 0 — no violations.
- [ ] Steam depot manifest reviewed; no files from `~/.convsim/models/` are staged.
- [ ] Steam depot manifest reviewed; no `.gguf`, `.bin`, `.safetensors`, `.pt`, `.pth`, or `.ckpt` weight files are included.
- [ ] Steam depot manifest reviewed; no unapproved binary payloads (large pickle, NumPy, or ONNX files; any `models/` subdirectory) are included.
- [ ] Depot contents match the approved binary payload list in `publishing/STEAM_DEPOT_CONTENTS.md`.
- [ ] Documentation files carrying CC-BY-4.0 attribution requirements are either excluded from the depot or accompanied by correct attribution in the credits screen.
- [ ] `LICENSE` and `NOTICE` files are present at the depot root for all three platforms.
- [ ] `NOTICE` file includes licence entries for all bundled runtimes (Whisper.cpp MIT, sherpa-onnx/Kokoro Apache 2.0, llama.cpp MIT, WebView2 on Windows).

### SR-09 — Private beta sign-off

Complete before submitting to Valve for private beta review.

| Gate | Owner | Pass / Fail | Date | Notes |
|------|-------|-------------|------|-------|
| SR-01 Offline smoke | Platform team | | | |
| SR-02 Privacy boundaries | Platform team | | | |
| SR-03 Microphone handling | Platform team | | | |
| SR-04 Model download transparency | Platform team | | | |
| SR-05 Content policy enforcement | Content team | | | |
| SR-06 Licensing audit | Platform team | | | |
| SR-07 Steam platform | Platform team | | | |
| SR-08 Depot content audit | Platform team | | | |
| Full `docs/release-checklist.md` Part A | CI | | | |
| Full `docs/release-checklist.md` Parts B + C | Platform team | | | |

All gates must show **Pass** before the private beta depot is submitted to Valve.
Any **Fail** must have a tracked issue with an owner and a target date before the
team is unblocked.

---

## Risk register summary

| ID | Area | Release-blocking | Status |
|----|------|-----------------|--------|
| PR-01 | Privacy | YES | MITIGATED |
| PR-02 | Privacy | YES | MITIGATED |
| PR-03 | Privacy | YES | MITIGATED |
| PR-04 | Privacy | YES | OPEN |
| PR-05 | Privacy | NO | OPEN |
| AU-01 | Privacy / Platform | YES | OPEN |
| AU-02 | Platform | YES | OPEN |
| AU-03 | Platform | YES | OPEN |
| MD-01 | Privacy / Platform | YES | MITIGATED |
| MD-02 | Safety / Privacy | YES | MITIGATED |
| MD-03 | Licensing | YES | OPEN |
| MD-04 | Licensing / Distribution | YES | MITIGATED |
| CP-01 | Safety | YES | MITIGATED |
| CP-02 | Privacy / Safety | YES | MITIGATED |
| CP-03 | Safety / Platform | YES | MITIGATED |
| CP-04 | Safety | YES | MITIGATED |
| LI-01 | Licensing | YES | OPEN |
| LI-02 | Licensing | NO | OPEN |
| LI-03 | Licensing | YES | OPEN |
| SP-01 | Platform | YES | OPEN |
| SP-02 | Platform | YES | OPEN |
| SP-03 | Platform | NO | OPEN |
| SP-04 | Platform | YES | OPEN |
| SP-05 | Platform / Licensing | NO (deferred) | DEFERRED |

---

## Links

- [`publishing/STEAM_STORE_PAGE.md`](STEAM_STORE_PAGE.md) — canonical store copy, system requirements, genres/tags, age disclosures, and store review checklist (SR-07 reference)
- [`publishing/STEAM_ASSETS_SPEC.md`](STEAM_ASSETS_SPEC.md) — capsule art, screenshot, and trailer production briefs
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — app identity, depot layout, and CI credentials
- [`publishing/STEAM_DEPOT_CONTENTS.md`](STEAM_DEPOT_CONTENTS.md) — authoritative depot content specification, approved binary payload list, and audit instructions (SR-08 reference)
- [`docs/STEAM_ROADMAP.md`](../docs/STEAM_ROADMAP.md) — release train, principles, and model download transparency spec
- [`docs/model-download-policy.md`](../docs/model-download-policy.md) — model download rules, mirror policy, checksum policy, licence disclosure, retry/resume behaviour (MD-01–MD-04 reference)
- [`docs/pack-download-policy.md`](../docs/pack-download-policy.md) — pack download and import policy for official, community, and local-dev packs (CP-01–CP-04 reference)
- [`docs/privacy.md`](../docs/privacy.md) — local-first data handling details
- [`docs/network-security.md`](../docs/network-security.md) — runtime network enforcement
- [`docs/safety-policy.md`](../docs/safety-policy.md) — content policy, pack sandboxing, and prohibited categories
- [`docs/release-checklist.md`](../docs/release-checklist.md) — platform smoke matrix (Parts A–D)
- [`schemas/safety.schema.json`](../schemas/safety.schema.json) — safety policy schema
- [`schemas/pack.schema.json`](../schemas/pack.schema.json) — pack manifest schema
- [`model-registry/`](../model-registry/) — authoritative model checksums and license metadata
- [`scripts/depot-audit.sh`](../scripts/depot-audit.sh) — depot content audit script (Linux / macOS)
- [`scripts/depot-audit.ps1`](../scripts/depot-audit.ps1) — depot content audit script (Windows PowerShell)
