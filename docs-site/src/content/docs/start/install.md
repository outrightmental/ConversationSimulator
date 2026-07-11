---
title: "Installation"
description: "Download, verify, and install Conversation Simulator on Windows, macOS, or Linux, and set up your first local model."
sidebar:
  order: 1
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
- **Windows:** run the `.exe` installer. SmartScreen may warn about an
  unrecognised publisher — click **More info → Run anyway**.
- **Linux:** make the AppImage executable and run it directly — no
  installation needed:

  ```bash
  chmod +x conversation-simulator_<version>_amd64.AppImage
  ./conversation-simulator_<version>_amd64.AppImage
  ```

The app starts its local conversation engine automatically. If the home
screen reports that the engine did not start, see
[Troubleshooting](/start/troubleshooting/#engine-startup-failure).

:::note
The unsigned-build warnings disappear automatically once code-signing
certificates land (tracked in
[#235](https://github.com/outrightmental/ConversationSimulator/issues/235)).
:::

---

## 3. Install a local model

On first launch the app shows a **"No model loaded"** banner. Open
**Settings → Models**, pick a model, and accept its license to start the
download. No model weights are bundled with the installer, and every
download is verified against its SHA-256 checksum before loading.

The recommended starter is **Qwen3 4B Instruct Q4_K_M** (~2.5 GB,
Apache-2.0). See [Local models](/play/local-models/) for recommendations by
hardware.

The one-time model download is the only step that needs an internet
connection. After it completes, everything works offline.

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
- [Local models](/play/local-models/) — choose a model for your hardware
- [Troubleshooting](/start/troubleshooting/) — common setup problems
- [Platform notes](/play/platform-notes/) — Gatekeeper, SmartScreen, WebView2, audio permissions
