<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Beta Testing Guide

This guide covers how to join the Conversation Simulator beta, where to report
problems, and what makes a great bug report.

---

## How to join

The beta runs on the `main` branch.  There is no separate opt-in — if you can
build from source or install a pre-release build, you are a beta tester.

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh
./scripts/dev.sh
```

Steam early access releases are tagged `beta/*` in the repository.

---

## Where to report

### One-click reporting (recommended)

The fastest way to file a useful report:

1. Open the app and go to **Support** (sidebar or menu).
2. Click **Report a problem**.
3. Review the list of files that will be included — nothing is written yet.
4. Optionally check **Include last session metadata** to add turn count and
   scenario ID (no transcript content, ever).
5. Click **Create bundle** — the ZIP is saved locally and your crash-bundles
   folder opens so you can verify its contents.
6. Click **Open GitHub issue →** — a pre-filled issue form opens in your
   browser.
7. Attach the ZIP from step 5, fill in what happened, and submit.

The whole flow takes under a minute and gives the team everything needed to
reproduce most bugs.

### Manual reporting

If the app will not start or the Support screen is unreachable, open a
[Beta feedback / bug report][new-issue] issue manually.  Include:

- App version (shown in the title bar or `versions.json` in a crash bundle)
- OS and architecture (e.g. "macOS 14.6 Apple Silicon")
- A clear description of what happened and what you expected
- Steps to reproduce

[new-issue]: https://github.com/outrightmental/ConversationSimulator/issues/new?template=beta-report.yml&labels=beta-feedback

---

## Privacy

Conversation Simulator is **local-first**.  The diagnostics bundle the
one-click flow creates contains:

| File | Contents |
|------|----------|
| `versions.json` | App version, Python version, OS platform string |
| `system.txt` | OS name, release, CPU architecture |
| `config.json` | App settings; home-directory paths replaced with `~` |
| `preflight.json` | Runtime, STT, and TTS health snapshot (no user data) |
| `recent_errors.txt` | Last log lines at WARNING level or above |
| `session_metadata.json` | (opt-in only) Scenario ID, session state, turn count, timestamps |
| `crash-bundle.zip` | (if one exists) Most recent crash bundle — already redacted |
| `README.txt` | Privacy notice |

**What is never included:**

- Conversation transcripts or NPC responses
- Player input or audio recordings
- LLM prompts or model outputs
- Real filesystem paths (the username portion is replaced with `~`)

The bundle is written locally and never transmitted automatically.  You review
it before attaching it to an issue.

---

## What makes a great report

A report that gets fixed quickly includes:

1. **A single, reproducible behaviour** — one bug per issue.
2. **Exact steps** — numbered list, starting from app launch.
3. **Expected vs actual outcome** — what should have happened, what did happen.
4. **A diagnostics bundle** — created with **Support → Report a problem**; it
   captures versions and error logs so you don't have to paste them manually.
5. **No transcript content** — describe scenario-specific bugs in general
   terms; the team can reproduce them with any pack.

### Example of a good report

> **What happened:** After ending a conversation, the debrief screen loads but
> the score card never appears — it spins indefinitely.
>
> **Expected:** Score and strengths should appear within 5 seconds.
>
> **Steps:**
> 1. Launch app
> 2. Select "Job Interview Basics" → "The Executive Gauntlet"
> 3. Complete 4 turns and press "End conversation"
> 4. Debrief screen: spinner visible, score section never populates
>
> **Environment:** App 0.9.0-beta.3, macOS 14.6 Apple Silicon, Qwen3 8B Q4_K_M
>
> **Bundle attached:** crash-bundles/beta-report-20260710T141500Z.zip

---

## Scope of the beta

During the beta we are particularly interested in feedback on:

- **Local model compatibility** — does your model load and produce sensible
  responses?
- **Voice / STT / TTS** — transcription accuracy, TTS naturalness, VAD
  sensitivity.
- **Scenario packs** — logic errors, inconsistent NPC state, missing events.
- **Performance** — startup time, latency, memory use on lower-end hardware.
- **Installation** — setup script failures, missing dependencies.

Feature requests are welcome but lower priority until core stability is
established.  Use the [feature proposal template][feature] for those.

[feature]: https://github.com/outrightmental/ConversationSimulator/issues/new?template=feature_proposal.yml
