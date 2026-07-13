---
title: "Installation"
description: "Download, verify, and install Conversation Simulator on Windows, macOS, or Linux, and set up your first local model."
sidebar:
  order: 1
verified_against: v0.2.2
---

Conversation Simulator runs entirely on your computer — no cloud inference,
no account, no telemetry. You need a local model before any conversation can
start; the app downloads one on first run after you accept its license.

:::note
This guide covers installing the **pre-built application** — the right path
for almost everyone. Contributors who want to run the platform from source
should follow the [developer install](/dev/developer-install/) instead.
:::

---

## System requirements

| Requirement | Minimum | Notes |
|---|---|---|
| OS | macOS 13+, Ubuntu 22.04+, Windows 10 | macOS 12 Monterey is no longer supported (app minimum is macOS 13) |
| CPU | Any 64-bit x86 or Apple Silicon | Apple Silicon recommended for CPU inference |
| RAM | 8 GB | 16 GB recommended for standard-tier models |
| GPU VRAM | 0 GB (CPU fallback available) | 4 GB+ for the starter model; see [Local models](/play/local-models/) |
| Disk | 20 GB free | 3–15 GB for model weights plus app data |

---

## 1. Download and verify

Download the installer for your platform from the
[releases page](https://github.com/outrightmental/ConversationSimulator/releases):

| Platform | File |
|---|---|
| macOS (Apple Silicon) | `ConversationSimulator_<version>_aarch64.dmg` |
| macOS (Intel) | `ConversationSimulator_<version>_x64.dmg` |
| Linux (x86_64) | `conversation-simulator_<version>_amd64.AppImage` |
| Windows (x86_64) | `ConversationSimulator_<version>_x64-setup.exe` |

Verify the download against the `checksums-sha256.txt` file on the release page:

```bash
# macOS / Linux
shasum -a 256 ConversationSimulator_<version>_aarch64.dmg
```

```powershell
# Windows PowerShell
Get-FileHash "ConversationSimulator_<version>_x64-setup.exe" -Algorithm SHA256
```

---

## 2. Install and launch

- **macOS:** open the `.dmg` and drag the app to `/Applications`. On first
  launch, Gatekeeper may warn about an unidentified developer (pre-release
  builds are unsigned). Right-click the app → **Open** → **Open** to proceed.
- **Windows:** run the `.exe` installer. Windows 10/11 release builds are
  Authenticode-signed, so no SmartScreen warning appears. If you see one on
  a pre-release build, click **More info → Run anyway**.
- **Linux:** make the AppImage executable and run it directly — no
  installation needed:

  ```bash
  chmod +x conversation-simulator_<version>_amd64.AppImage
  ./conversation-simulator_<version>_amd64.AppImage
  ```

The app starts its local conversation engine automatically. If the home
screen reports that the engine did not start, see
[Troubleshooting](/start/troubleshooting/#engine-startup-failure).

---

## 3. Set up your AI (first launch)

On first launch the app shows the **welcome screen**. Click **Set me up**.

The app detects your hardware, selects the recommended model, shows you its
details and license, and asks you to confirm. After you confirm:

- A progress screen shows each installation stage (engine check → model
  download → verification → warmup).
- While the model downloads you can click **Play the tutorial while you
  wait** to try the simulator with scripted, non-AI responses.
- When all stages complete, click **Continue to Home** to start playing.

No model weights are bundled with the installer. The one-time download is
the only step that requires an internet connection — after it completes,
everything works offline.

Want to use Ollama or a custom model file instead? See
[Choosing how to run the AI](/play/ai-engine/).

---

## Beta builds — direct-download channel

Beta builds are published to GitHub Releases as versioned pre-releases
(e.g. `v0.1.0-beta.1`). They are distinct from the Steam beta branch.

### In-app update notice

The app checks for a new beta on launch and shows a non-intrusive banner on
the home screen when one is found. The banner never appears during an active
conversation session. Click **View notes** to open the release page, or
**Install** to open it and download the new build. The check is skipped
silently when you are offline.

### Rollback

Every beta release remains permanently downloadable from its versioned
release page (e.g., `releases/tag/v0.1.0-beta.1`). To roll back:

1. Download the installer from the previous versioned release page.
2. Install over the current version — the Windows installer and macOS DMG
   both support in-place downgrades.
3. Data created in a newer beta is forward-compatible with older betas at
   the same schema version (see [Schema versioning](/reference/schema-versioning/)).

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
