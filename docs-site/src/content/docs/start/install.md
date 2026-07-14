---
title: "Installation"
description: "Install Conversation Simulator on Windows, macOS, or Linux — from Steam, or by building the open-source code yourself."
sidebar:
  order: 1
verified_against: v0.2.3
---

Conversation Simulator runs entirely on your computer — no cloud inference,
no account, no telemetry. You need a local model before any conversation can
start; the app downloads one on first run after you accept its license.

There are exactly **two ways to get it**:

| | [Steam](#1-steam--the-ready-to-run-build) | [Build from source](#2-build-from-source--free) |
|---|---|---|
| **Cost** | $9.99 | Free |
| **You get** | A ready-to-run app: code-signed, notarized, auto-updating via Steam, Steam Deck–verified. The AI engine is bundled, so there is nothing to install separately. | The same software, built by you from the Apache-2.0 source. |
| **Best for** | Almost everyone. | Developers, and anyone who wants to inspect or modify the code. |

:::caution[There are no installers to download]
Conversation Simulator does **not** publish `.dmg`, `.exe`, `.msi`, `.deb`, or
`AppImage` downloads — not on GitHub, not on our website. Steam is the only
channel that ships prebuilt binaries. If you find an installer for this app
anywhere else, it did not come from us.

The GitHub releases page carries release notes and source tags only. To run the
free version, build it from source at a release tag (below).
:::

---

## System requirements

| Requirement | Minimum | Notes |
|---|---|---|
| OS | macOS 13+, Ubuntu 22.04+, Windows 10 | macOS 12 Monterey is no longer supported (app minimum is macOS 13) |
| CPU | Any 64-bit x86 or Apple Silicon | Apple Silicon recommended for CPU inference |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for the starter model; see [Choosing how to run the AI](/play/ai-engine/) |
| Disk | 20 GB free | 3–15 GB for model weights plus app data |

---

## 1. Steam — the ready-to-run build

Install **Conversation Simulator** from Steam on Windows, macOS, Linux, or Steam
Deck. Steam handles installation and updates; there is nothing else to download
and nothing to verify by hand.

The Steam build is code-signed on Windows, signed and notarized on macOS, and
ships with the AI engine bundled — so your first conversation can start while the
model is still downloading.

That is the whole procedure. Skip to [First launch](#3-first-launch).

---

## 2. Build from source — free

The engine is Apache-2.0 and the four official scenario packs are CC BY 4.0, so
you can always build and run the app yourself at no cost. It is the same
software; you are supplying the build instead of paying for one.

Check out a **release tag** rather than `main` — tags are the versions we test
and ship:

```bash
git clone https://github.com/outrightmental/ConversationSimulator.git
cd ConversationSimulator
git checkout v0.2.3        # latest release tag
```

Then follow the [developer install](/dev/developer-install/), which covers
prerequisites (Node, pnpm, Python, Rust) and building the desktop app.

Note that a source build is not code-signed. macOS Gatekeeper will warn about an
unidentified developer on first launch: right-click the app → **Open** → **Open**.
On Windows, SmartScreen may show *"Windows protected your PC"* — click
**More info → Run anyway**. This is expected for software you built yourself; the
signed builds are the ones distributed through Steam.

---

## 3. Set up your AI (first launch)

However you got the app, the first launch is the same. The app starts its local
conversation engine automatically; if the home screen reports that the engine did
not start, see [Troubleshooting](/start/troubleshooting/#engine-startup-failure).

On first launch the app shows the **welcome screen**. The **Set me up** card
names the recommended model for your hardware and shows its download size and
license. Click **Set me up** to begin — the download starts right away.

- A progress screen shows each installation stage (engine check → model
  download → verification → warmup).
- While the model downloads you can click **Start now** on the **Have your
  first conversation** card to try the simulator with scripted, non-AI
  responses.
- When all stages complete, click **Continue to Home** to start playing.

No model weights are bundled with the app. The one-time download is the only
step that requires an internet connection — after it completes, everything works
offline.

Want to use Ollama or a custom model file instead? See
[Choosing how to run the AI](/play/ai-engine/).

---

## Updates and rollback

**On Steam,** Steam handles updates. Beta builds are published to the Steam
**beta branch** — opt in from the app's Properties → Betas in your Steam library.
To roll back, pick an earlier build from that same menu.

There is no in-app updater and no direct-download beta channel: the app never
polls GitHub for a new version, because no binaries are published there.

**From source,** update by checking out a newer release tag and rebuilding; roll
back by checking out an earlier one. Data created in a newer version is
forward-compatible with older versions at the same schema version (see
[Schema versioning](/reference/schema-versioning/)).

---

## Data locations

| Path | Purpose |
|---|---|
| `~/.convsim/db/` | Session database (SQLite) |
| `~/.convsim/data/` | Exported data and pack cache |
| `~/.convsim/logs/` | Runtime logs |
| `~/.convsim/models/llm/` | Downloaded model weights |

Override any of these with environment variables: `CONVSIM_DB_DIR`,
`CONVSIM_DATA_DIR`, `CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR`.

---

## Next steps

- [Quickstart](/start/quickstart/) — run your first conversation
- [Choosing how to run the AI](/play/ai-engine/) — built-in engine, Ollama, GGUF, and hardware recommendations
- [Troubleshooting](/start/troubleshooting/) — common setup problems
- [Platform notes](/play/platform-notes/) — Gatekeeper, SmartScreen, WebView2, audio permissions
