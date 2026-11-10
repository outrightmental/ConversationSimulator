---
title: "Installation"
description: "Install Conversation Simulator on Windows, macOS, or Linux — from Steam, or by building the open-source code yourself."
sidebar:
  order: 1
verified_against: v0.4.0
---

Conversation Simulator runs entirely on your computer — no cloud inference,
no account, no telemetry. You need a local model before any conversation can
start; the app downloads one on first run, and shows its size and license
before you begin.

There are exactly **two ways to get it**:

| | [Steam](#1-steam--the-ready-to-run-build) | [Build from source](#2-build-from-source--free) |
|---|---|---|
| **Cost** | $9.99 | Free |
| **You get** | A ready-to-run app for Windows, macOS (Apple Silicon), Linux and Steam Deck: code-signed, notarized, and updated through Steam. The AI engine is bundled, so there is nothing to install separately. | The same software, built by you from the Apache-2.0 source. |
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
| OS | macOS 14+, Ubuntu 22.04+, Windows 10 (build 19041 or newer) | macOS 13 Ventura and earlier are not supported: the bundled AI engine needs macOS 14 |
| CPU | Any 64-bit x86 or Apple Silicon | On macOS, Apple Silicon is recommended: the AI engine uses Metal acceleration there. The Steam build for macOS is built for Apple Silicon only, so an Intel Mac needs a source build |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for the starter model; see [Choosing how to run the AI](/play/ai-engine/) |
| Disk | 5 GB free | 20 GB recommended. Model weights take 3–15 GB depending on tier, plus app data |

---

## 1. Steam — the ready-to-run build

Install **Conversation Simulator** from Steam on Windows, macOS (Apple Silicon),
Linux, or Steam Deck. Steam handles installation and updates; there is nothing
else to download and nothing to verify by hand.

The Steam build is code-signed on Windows, signed and notarized on macOS, and
ships with the AI engine bundled, so there is nothing to install separately.

That is the whole procedure. Skip to [Set up your AI](#3-set-up-your-ai-first-launch).

---

## 2. Build from source — free

The engine and the First Words tutorial are Apache-2.0 and the official scenario
packs are CC BY 4.0, so you can always build and run the app yourself at no
cost. It is the same software; you are supplying
the build instead of paying for one.

Check out a **release tag** rather than `main` — tags are the versions we test
and ship:

```bash
git clone https://github.com/outrightmental/ConversationSimulator.git
cd ConversationSimulator
git checkout v0.4.0        # latest release tag
```

Then follow the [developer install](/dev/developer-install/), which covers the
prerequisites (Python, Node.js, pnpm) and running the app from source. Building
the desktop app itself also needs the Rust toolchain; the
[Platform notes](/play/platform-notes/) list the build prerequisites for each OS.

Note that a source build is not code-signed. macOS Gatekeeper will warn about an
unidentified developer on first launch: right-click the app → **Open** → **Open**.
On Windows, SmartScreen may show *"Windows protected your PC"* — click
**More info → Run anyway**. This is expected for software you built yourself; the
signed builds are the ones distributed through Steam.

---

## 3. Set up your AI (first launch)

However you got the app, the first launch is the same. The app starts its local
conversation engine automatically; if the app reports that the conversation
engine did not start, see
[Troubleshooting](/start/troubleshooting/#engine-startup-failure).

On first launch the app shows the **welcome screen**. It asks how familiar you
are with AI language models; your answer sets how technical the app's wording
is, and you can change it later under **Settings → Wording**. The **Set me up**
card shows the download size and license of the recommended model. Click
**Set me up** to begin. The app first checks that it can write to its data
folder and that the disk has room for the model; if either needs your attention
it shows a **Getting things ready** screen, otherwise the download starts.

- A progress screen lists each installation stage: getting the AI engine
  (shown as skipped when the engine is already there, as in the Steam build),
  downloading the model, verifying its SHA-256 checksum, the model's first
  launch, and preparing scenarios.
- While the model downloads, the same screen explains how to play and previews
  your first scenarios.
- When all stages complete, the app opens the **Scenario Library**. Pick a
  scenario to start playing.

The recommended model is the registry's starter entry, currently
**Qwen3 4B Instruct 2507 Q4_K_M** (2.5 GB, Apache-2.0). It is saved in the
`models/llm/` folder under the data folder (see [Data locations](#data-locations)).

No model weights are bundled with the app. The one-time download is the only
step that requires an internet connection — after it completes, everything works
offline.

Want to use Ollama or a custom model file instead? Expand **Advanced: use
Ollama or a local GGUF file** on the welcome screen, or see
[Choosing how to run the AI](/play/ai-engine/).

---

## Updates and rollback

**On Steam,** Steam handles updates; the Steam build has no in-app updater.
Pre-release builds go to the Steam **beta** branch first (opt in from the app's
Properties → Betas in your Steam library). If a release has to be withdrawn, we
set the previous build live again and Steam delivers it; there is nothing for
you to do.

There is no direct-download channel: no installers or beta builds are published
on GitHub, so the only prebuilt binaries come through Steam.

**From source,** update by checking out a newer release tag and rebuilding; roll
back by checking out an earlier one. Data created in a newer version is
forward-compatible with older versions at the same schema version (see
[Schema versioning](/reference/schema-versioning/)).

---

## Data locations

The desktop app keeps its data under one folder in your platform's local
app-data location:

| Platform | Data folder |
|---|---|
| macOS | `~/Library/Application Support/com.outrightmental.convsim/` |
| Windows | `%LOCALAPPDATA%\com.outrightmental.convsim\` |
| Linux and Steam Deck | `~/.local/share/com.outrightmental.convsim/` (under `$XDG_DATA_HOME` if that is set) |

Inside it:

| Folder | Purpose |
|---|---|
| `db/` | Session database (SQLite) |
| `data/` | General app data. Raw microphone recordings go to `data/audio/` only while **Save raw audio recordings (advanced)** is turned on; the switch sits under **Show advanced** at the bottom of Settings |
| `logs/` | Runtime logs |
| `models/llm/` | Downloaded model weights |
| `packs/` | Installed scenario packs: copies of the official packs, packs you import, and the Creator Workbench's `local-dev/` packs |
| `exports/` | Created and listed in Settings, but nothing is written here yet: the **Export** button in Settings hands you the session as a download named `session-<id>.json` |
| `cache/` | Created and listed in Settings, but nothing is written here yet: the voice synthesis cache goes to `~/.convsim/tts_cache/` |
| `crashes/` | Crash bundles and diagnostics bundles |

**Settings → Local folders** lists all of these except `db/` (as Data, Logs,
Models, Packs, Exports, Cache and Crash bundles), shows the exact paths and
opens them. Move single folders with `CONVSIM_DB_DIR`, `CONVSIM_DATA_DIR`,
`CONVSIM_LOG_DIR`, `CONVSIM_MODELS_DIR`, `CONVSIM_PACKS_DIR`, `CONVSIM_EXPORTS_DIR`,
`CONVSIM_CACHE_DIR` and `CONVSIM_CRASH_BUNDLES_DIR`; the desktop shell passes them
through to convsim-core. `CONVSIM_DATA_ROOT` moves the whole tree, but only when
convsim-core runs without the desktop shell: the shell always sets it to the
folder above. If you run the services from source without the desktop shell,
convsim-core uses `%LOCALAPPDATA%\outrightmental\convsim\` on Windows and
`~/.local/share/convsim/` on Linux instead. Run that way, convsim-core copies
data from older builds that used `~/.convsim/` into the new folder on first
start, but only while the folder is still empty, and never the model weights, so
download the model again. The desktop app does not copy it (the shell creates the
folder first); [Troubleshooting](/start/troubleshooting/#data-dir-writable) says how to bring
old sessions across by hand.

A few things still live under `~/.convsim/`: the AI engine that a source build
downloads on first run (`~/.convsim/bin/`; the Steam build has it bundled), the
voice input and voice activity detection models (`~/.convsim/models/stt/` and
`~/.convsim/models/vad/`, where the download scripts under `runtimes/` put them)
and the voice synthesis cache (`~/.convsim/tts_cache/`). When you run from source
with `scripts/dev.sh` or `scripts/dev.ps1`, logs go to `~/.convsim/logs/` as well
unless you set `CONVSIM_LOG_DIR`.

---

## Next steps

- [Quickstart](/start/quickstart/) — run your first conversation
- [Choosing how to run the AI](/play/ai-engine/) — built-in engine, Ollama, GGUF, and hardware recommendations
- [Troubleshooting](/start/troubleshooting/) — common setup problems
- [Platform notes](/play/platform-notes/) — Gatekeeper, SmartScreen, WebView2, audio permissions
