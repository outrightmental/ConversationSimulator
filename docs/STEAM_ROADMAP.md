<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Edition Roadmap Addendum

> **Purpose of this document:** Define the product target for shipping
> Conversation Simulator as a free, sponsored Steam edition for non-technical
> players — without compromising the local-first, open-source, no-telemetry
> principles of the base project. Every downstream Steam-release issue should
> reference this document as its shared product target.

---

## Release principles

### Free on Steam, sponsored by Outright Mental

The Steam edition is and will remain **free to download and play**. There is no
base purchase price, no subscription, and no pay-to-unlock core content.
Outright Mental sponsors the distribution costs (Steam partner fees, code
signing, CI infrastructure, release tooling) so the project can reach
non-technical players without charging them.

### Local-first play, no exceptions

The Steam edition makes the same guarantee as the open-source build:

> Conversations, prompts, transcripts, audio, and model outputs stay on the
> player's machine. Nothing is sent to any server during play. Model and pack
> downloads happen only when the player explicitly requests them.

This is backed by code and CI gates, not just policy. See
[`privacy.md`](privacy.md) and [`network-security.md`](network-security.md) for
the runtime enforcement details.

### No telemetry

The Steam edition ships with telemetry absent, matching the open-source build.
No usage analytics, session counts, feature-use events, or background pings are
transmitted. If telemetry is ever proposed for a future milestone it will require
explicit opt-in, documented notice, and a default-off posture — and it will never
include conversation content.

### Explicit model and pack downloads only

No model weights are silently bundled in the installer or downloaded without the
player's knowledge. Every model download must:

- Display the **model name and source** before any bytes transfer.
- Show the **license** (e.g. Apache 2.0, Llama Community License) so the player
  understands the terms.
- Show the **download size** so the player can plan for disk space and bandwidth.
- Show the **SHA-256 checksum** that will be verified after download.
- Show the **destination path** on the player's machine where the file will land.

Players must confirm each download. Cancelling a download must leave no partial
files. Pack downloads follow the same rules.

### No paid marketplace in v1

The Steam release does not include a paid content marketplace. Community packs
may be distributed outside the app (GitHub, itch.io, direct links), but the
in-app experience ships no payment rails, no premium pack tier, and no
microtransactions in v1. Post-launch marketplace exploration is recorded as
stage 5 of the [release train](#release-train) and is explicitly deferred.

---

## Release train

Work proceeds through the following stages. Each stage is a prerequisite for
the next. Do not begin a stage until the prior stage's acceptance criteria are
met and its tracking issue is closed.

| Stage | Description | Entry criterion |
|-------|-------------|-----------------|
| **1. GitHub MVP** | Open-source build reaches Milestone 1: stable text loop, voice I/O, workbench, official packs, offline smoke gate, full docs. | All [ROADMAP.md](../ROADMAP.md) Milestone 1 items are checked off. |
| **2. Packaged desktop alpha** | Tauri desktop app bundles `convsim-core` as a sidecar. Single installer on Windows, macOS, Linux. No Steam involvement yet. | GitHub MVP is tagged. Installer boots without CLI setup. Offline smoke test passes from the installed app. |
| **3. Steam private beta** | App is submitted to the Steam partner portal. Invited testers (developers, Outright Mental staff, select community members) validate the Steam overlay, controller navigation, and platform-specific quirks. | Packaged desktop alpha passes internal QA on all three desktop platforms. Steam page draft is approved by Valve. |
| **4. Public free Steam release** | App is published as a free title on Steam. All four official packs are available. Model Manager UI is stable. | Steam private beta exit criteria are met. Code signing is in place on macOS and Windows. Steam Deck verification is complete (see [Target platforms](#target-platforms)). |
| **5. Post-launch: marketplace exploration** | Evaluate whether a community pack browser or optional Outright Mental-curated content makes sense as a zero-cost or patron-supported layer. No decision has been made; this is a research milestone only. | Public release has been live for at least 90 days. Community feedback and usage signals inform the evaluation. |

---

## Target platforms

The Steam edition targets the following platforms at public release. All four
must pass the release smoke matrix (see
[`docs/release-checklist.md`](release-checklist.md)) before the public release
gate is opened.

| Platform | Tier | Notes |
|----------|------|-------|
| **Windows 10 / 11 (x86-64)** | Required | Primary target. NSIS installer. SmartScreen code signing required. |
| **macOS 13+ (Apple Silicon and Intel)** | Required | Universal binary preferred. Gatekeeper notarisation required. `.dmg` installer. |
| **Linux (x86-64, glibc)** | Required | AppImage or Flatpak. Tested on Ubuntu 22.04 LTS and Fedora 40. |
| **Steam Deck / SteamOS (x86-64)** | Required for public release | Verified (not Playable) tier. Controller navigation must work in the main menu and model manager. Keyboard input must work in-game. Battery impact must be documented. |

### Steam Deck verification checklist

Steam Deck verification is a Valve process; meeting these criteria makes
approval likely but Valve has final say.

- [ ] The app launches in Gaming Mode without additional setup steps.
- [ ] All menus are navigable with the Steam Deck controller (D-pad + A/B/X/Y, left stick, trackpad).
- [ ] The on-screen keyboard appears automatically for any text-input field.
- [ ] Text is readable at 1280×800 without zooming.
- [ ] No required UI element is hidden behind a mouse-only interaction.
- [ ] The offline smoke test passes under SteamOS 3.x.

---

## Model download transparency

This section expands the release principle into a specification that the model
manager UI must satisfy before the packaged desktop alpha stage opens.

### Required display before any download begins

```
Model:       Qwen3 4B Instruct (Q4_K_M)
Source:      Hugging Face — Qwen/Qwen3-4B-GGUF
License:     Apache 2.0 (https://www.apache.org/licenses/LICENSE-2.0)
Size:        2.6 GB
Checksum:    SHA-256 — a3b1c2...  (verified after download)
Destination: ~/.convsim/models/qwen3-4b-q4_k_m.gguf
```

All six fields are mandatory. A model entry that omits any field must not appear
in the download UI.

### Verification after download

After the file transfer completes, the model manager must:

1. Compute the SHA-256 checksum of the downloaded file locally.
2. Compare it against the value from the model registry.
3. If the checksums match: mark the model as installed and available.
4. If the checksums do not match: delete the partial file, display an error, and
   offer to retry. Never leave a failed download in place.

The model registry file (`model-registry/`) is the authoritative source of
checksums. A new model entry must not be merged into the registry without a
verified checksum from the original source.

### What "explicit" means

A download is explicit if and only if the player (or developer, during setup)
pressed a labelled **Download** button while the metadata panel described above
was visible. Downloads triggered by:

- App startup
- Installer scripts
- Background update checks
- Silent fallbacks when a model is missing

…are not explicit and are **not permitted** in the Steam edition.

---

## Issue dependency conventions

Steam-roadmap issues are sequenced. A downstream issue that depends on an
upstream issue must not be started until the upstream issue is merged and
closed. Enforcing this prevents work that assumes a foundation that does not
yet exist.

### How to express a dependency in an issue

Add a **Prerequisites** section to the issue body:

```markdown
## Prerequisites

- Blocked by #NNN — [short description of what that issue delivers]
```

If an issue has no prerequisites, say so explicitly:

```markdown
## Prerequisites

None. This is an unblocked issue.
```

### How to express a dependency in a PR

Add a **Blocked by** line to the PR body if the PR should not be merged until
another PR lands:

```markdown
Blocked by #NNN
```

GitHub does not natively enforce merge order, so it is the author's
responsibility to check that upstream PRs are merged before asking for a review
on a dependent PR.

### Milestone assignments

| Milestone | Scope |
|-----------|-------|
| **Milestone 1** | GitHub MVP polish (screenshots, code signing groundwork, accessibility baseline) |
| **Milestone 2** | Packaged desktop alpha (Tauri sidecar, auto-update, real-model CI, voice polish) |
| **Milestone 3** | Steam private beta (Steam Deck verification, Steam overlay integration, beta tester program) |
| **Milestone 4** | Public free Steam release |
| **Milestone 5** | Post-launch (marketplace exploration, community pack browser, analytics opt-in) |

Assign every Steam-roadmap issue to one of these milestones. Issues without a
milestone are considered unscoped and will be left in triage.

---

## Steam roadmap issue set

The following GitHub issues implement this roadmap in sequence. A downstream
issue must not be started until the upstream issue is merged and closed.

| Title | Document delivered | Stage dependency |
|-------|-------------------|-----------------|
| [[Steam Roadmap] Add Steam edition roadmap addendum and release principles](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-roadmap-addendum+in%3Atitle) | [docs/STEAM_ROADMAP.md](STEAM_ROADMAP.md) | Stage 1 prerequisite |
| [[Steam Roadmap] Create Steam compliance and risk register for local-AI distribution](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-compliance-risk-register+in%3Atitle) | [publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) | Stage 3 prerequisite |
| [[Steam Roadmap] Define Steam MVP scope and release gates](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+steam-mvp-scope+in%3Atitle) | [docs/steam-mvp-scope.md](steam-mvp-scope.md) | Stage 2 prerequisite |

All open and closed issues in this work stream:
[GitHub — issues with `[Steam Roadmap]` prefix](https://github.com/outrightmental/ConversationSimulator/issues?q=is%3Aissue+%5BSteam+Roadmap%5D+in%3Atitle)

---

## Links

- [ROADMAP.md](../ROADMAP.md) — base project roadmap (MVP acceptance criteria, build order, status)
- [steam-mvp-scope.md](steam-mvp-scope.md) — minimum playable release features, optional targeted features, pass/fail gates, and post-launch deferrals
- [post-alpha-issues.md](post-alpha-issues.md) — triaged items deferred from the alpha
- [privacy.md](privacy.md) — local-first promise and data handling details
- [network-security.md](network-security.md) — runtime network enforcement
- [release-checklist.md](release-checklist.md) — platform smoke matrix
- [model-registry/](../model-registry/) — authoritative model checksums and license metadata
- [GitHub Milestones](https://github.com/outrightmental/ConversationSimulator/milestones) — issue tracking
