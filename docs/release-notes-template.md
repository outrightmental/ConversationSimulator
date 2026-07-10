<!-- SPDX-License-Identifier: CC-BY-4.0 -->
<!-- ─────────────────────────────────────────────────────────────────────────── -->
<!-- RELEASE NOTES TEMPLATE                                                     -->
<!-- Copy this file, replace each {{PLACEHOLDER}}, and delete these comments.  -->
<!-- ─────────────────────────────────────────────────────────────────────────── -->

# Conversation Simulator {{VERSION}} — Release Notes

> **Alpha release** — This build is an early preview. Expect rough edges and
> breaking changes between alpha versions. File bugs at
> <https://github.com/outrightmental/ConversationSimulator/issues>.

---

## What's new in {{VERSION}}

<!-- List the most important changes since the previous release. -->

- {{CHANGE_1}}
- {{CHANGE_2}}

---

## Download and verify

Installers for this release:

| Platform | File | SHA-256 |
|---|---|---|
| macOS (Apple Silicon) | `ConversationSimulator_{{VERSION}}_aarch64.dmg` | see `checksums-sha256.txt` |
| macOS (Intel) | `ConversationSimulator_{{VERSION}}_x64.dmg` | see `checksums-sha256.txt` |
| Linux (x86_64) | `conversation-simulator_{{VERSION}}_amd64.AppImage` | see `checksums-sha256.txt` |
| Windows (x86_64) | `ConversationSimulator_{{VERSION}}_x64-setup.exe` | see `checksums-sha256.txt` |

Verify before running:

```bash
# macOS / Linux
shasum -a 256 <filename>
```

```powershell
# Windows PowerShell
Get-FileHash "<filename>" -Algorithm SHA256
```

Compare the output against `checksums-sha256.txt` attached to this release.

---

## System requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | macOS 13, Ubuntu 22.04, Windows 10 (build 19041+) | Latest stable |
| CPU | 64-bit x86 or Apple Silicon | Apple Silicon M1 or newer |
| RAM | 8 GB | 16 GB |
| Disk | 5 GB free | 20 GB free (headroom for multiple models) |
| Microphone | Optional | Required for voice input |

Run the pre-flight check before first launch:

```bash
./scripts/first-run-check.sh        # macOS / Linux
.\scripts\first-run-check.ps1       # Windows PowerShell
```

---

## Installation

### macOS

1. Download the `.dmg` for your chip (Apple Silicon = aarch64, Intel = x64).
2. Open the `.dmg` and drag **Conversation Simulator** to `/Applications`.
3. **First launch:** macOS Gatekeeper will warn that the app is from an
   unidentified developer — this release is **not code-signed**. To open it:
   - Right-click (or Control-click) the app icon → **Open** → **Open**.
   - In System Settings → Privacy & Security → scroll down and click **Open Anyway**.

### Windows

1. Download `ConversationSimulator_{{VERSION}}_x64-setup.exe`.
2. Run the installer. Windows Defender SmartScreen may warn about an
   **unrecognised publisher** — click **More info → Run anyway**.
3. Launch from the Start Menu.

### Linux

1. Download the `.AppImage` file.
2. Make it executable: `chmod +x conversation-simulator_{{VERSION}}_amd64.AppImage`
3. Run: `./conversation-simulator_{{VERSION}}_amd64.AppImage`

---

## Local model — not bundled

No language model weights are included in the installer. On first launch, the
app opens the **Model Manager**, which lists curated models with size, license,
and hardware requirements. You must accept the model license before a download
begins. The downloaded file is verified against its SHA-256 checksum before
loading.

**Why not bundled?** Model weights are large (2–15 GB), carry their own
licenses (some restrict redistribution), and the right model depends on your
hardware. Downloading on first run respects those licenses and keeps the
installer small.

---

## Privacy and safety

- **All inference runs locally.** No audio, text, or session data leaves your
  computer during play. The app requires internet access only for the initial
  model download and for optional pack updates.
- **No telemetry.** The app does not phone home, collect crash reports, or send
  usage statistics.
- **Content filtering.** The simulator applies keyword pre-checks and output
  validation before presenting NPC dialogue. See
  [safety-policy.md](safety-policy.md) for details.
- **Microphone permission.** The OS will prompt for microphone access on first
  use of voice input. You can use the app in text-only mode without granting
  this permission.
- **Session data stays on your machine.** Session transcripts and debrief
  reports are stored in `~/.convsim/` (macOS/Linux) or
  `%USERPROFILE%\.convsim\` (Windows). You can delete this directory at any
  time to remove all local data.

---

## Known limitations in this release

- **Source install only for full functionality.** The packaged desktop app
  wraps the web UI but does not yet bundle the backend server (`convsim-core`).
  Backend-dependent features (Model Manager, Scenario Library, Conversation,
  Debrief, Settings) require running `convsim-core` separately. See
  [docs/install.md](install.md) for the developer install path.
- **No auto-update.** Download new releases manually from the releases page.
- **No code signing.** macOS and Windows will warn about unverified publishers
  (see installation instructions above).
- **Speech input / output** requires additional local runtimes. Speech-to-text
  uses whisper.cpp (`./runtimes/whisper_cpp/download-runtime.sh`); text-to-speech
  uses a local Kokoro server. See the runtime READMEs under `runtimes/` for setup.

---

## Source build

To build from source on a clean checkout:

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh            # install deps, create Python venv
pnpm --filter @convsim/web build
pnpm --filter @convsim/desktop build
# installer appears in apps/desktop/src-tauri/target/release/bundle/
```

See [docs/install.md](install.md) and [docs/platform-notes.md](platform-notes.md)
for full prerequisites and platform-specific notes.

---

## Reporting bugs

Open an issue at <https://github.com/outrightmental/ConversationSimulator/issues>.
Include:

- OS and version
- Output of `./scripts/first-run-check.sh` (or `first-run-check.ps1`)
- Log files from `~/.convsim/logs/`
- Steps to reproduce
