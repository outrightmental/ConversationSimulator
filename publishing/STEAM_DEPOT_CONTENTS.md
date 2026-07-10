<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Depot Contents

> **Purpose:** Define exactly what ships in each Steam depot and what players
> explicitly download after first launch. This is the authoritative reference for
> the depot content audit gate (SR-08) and the SteamPipe VDF templates in
> `steam/`.
>
> **Compliance:** Enforced by `scripts/depot-audit.sh` / `depot-audit.ps1` and
> the audit step in `.github/workflows/steam-deploy.yml`. No file category
> marked **FORBIDDEN** may appear in any depot under any circumstance. See the
> full risk register at
> [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

---

## Policy summary

| Category | Ships in depot | Downloaded post-launch |
|----------|---------------|------------------------|
| App shell (Tauri executable) | YES — all platforms | No |
| Python backend (`convsim-core`) | YES — bundled in app resources | No |
| Runtime sidecars (llama-server, whisper-cli, sherpa-onnx-offline-tts) | YES — `runtimes/` directory | No |
| Official scenario packs (4 packs) | YES — bundled in app resources | No |
| UI assets (icons, fonts, web bundle) | YES — embedded in app bundle | No |
| License files (`LICENSE`, `NOTICE`) | YES — depot root | No |
| LLM model weights (`.gguf`, `.safetensors`, etc.) | **FORBIDDEN** — see MD-04 | YES — explicit player download via model manager |
| Community scenario packs | No | YES — manual import by player (v1); in-app browser deferred to Stage 5 |
| Debug symbols (`.pdb`, `.dSYM`) | No | No |
| Developer artefacts (`.venv`, `__pycache__`, etc.) | **FORBIDDEN** | No |
| Secret or credential files | **FORBIDDEN** | No |
| Test fixtures | **FORBIDDEN** | No |

---

## Depot layout by platform

Each platform has a dedicated Steam depot. Depot IDs are tracked in
[`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md). The
SteamPipe VDF templates in `steam/` configure the file mappings and exclusions.

### Windows depot (`depot_windows.vdf.tpl`)

**Content root:** `steam-content/windows/` (populated by the deploy workflow)

```
ConversationSimulator.exe         # Tauri shell — main app entry point
WebView2Loader.dll                # Microsoft WebView2 runtime loader
*.dll                             # Tauri / WRY / WebView2 support DLLs
resources/
  bin/
    convsim-core.exe              # PyInstaller-bundled Python backend
  runtimes/
    llama-server.exe              # llama.cpp inference server (LLM)
    whisper-cli.exe               # Whisper.cpp speech-to-text binary
    sherpa-onnx-offline-tts.exe   # Kokoro TTS via sherpa-onnx
  packs/
    job-interview-basic/          # Official scenario pack (bundled)
    everyday-negotiation/         # Official scenario pack (bundled)
    language-cafe/                # Official scenario pack (bundled)
    difficult-conversations/      # Official scenario pack (bundled)
LICENSE                           # Apache 2.0 (top-level, not inside resources/)
NOTICE                            # Third-party licence notices (MIT, Apache 2.0)
```

**Excluded by VDF `FileExclusion`:**

| Pattern | Reason |
|---------|--------|
| `*.pdb` | Debug symbols — not useful to players |
| `*.gguf` | Model weight files — compliance rule MD-04 |
| `*.bin` | Model weight files — compliance rule MD-04 |
| `*.safetensors` | Model weight files — compliance rule MD-04 |
| `*.pt` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.pth` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.ckpt` | Model checkpoints — compliance rule MD-04 |

### macOS depot (`depot_macos.vdf.tpl`)

**Content root:** `steam-content/macos/`

The macOS depot ships a notarised `.app` bundle. A universal binary (Apple
Silicon + Intel) is preferred; separate arm64 and x86-64 slices are acceptable
if a universal build is not yet available.

```
ConversationSimulator.app/
  Contents/
    MacOS/
      ConversationSimulator         # Tauri shell binary
    Resources/
      bin/
        convsim-core                # PyInstaller-bundled Python backend
      runtimes/
        llama-server                # llama.cpp inference server
        whisper-cli                 # Whisper.cpp STT binary
        sherpa-onnx-offline-tts     # Kokoro TTS via sherpa-onnx
      packs/
        job-interview-basic/
        everyday-negotiation/
        language-cafe/
        difficult-conversations/
    Info.plist
    _CodeSignature/                 # Apple code-signature bundle (mandatory)
LICENSE                             # Apache 2.0
NOTICE                             # Third-party licence notices
```

**Requirements:**
- The entire `.app` bundle **must be notarised** with an Apple Developer ID
  certificate before Stage 3 (private beta) depot submission. See gate G3-01 in
  `docs/steam-mvp-scope.md` and risk SP-04 in the compliance register.
- The `.app` bundle must pass `spctl --assess --type execute` on a clean macOS
  install.

**Excluded by VDF `FileExclusion`:**

| Pattern | Reason |
|---------|--------|
| `*.dSYM/*` | Xcode debug symbol bundles — not useful to players |
| `*.gguf` | Model weight files — compliance rule MD-04 |
| `*.bin` | Model weight files — compliance rule MD-04 |
| `*.safetensors` | Model weight files — compliance rule MD-04 |
| `*.pt` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.pth` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.ckpt` | Model checkpoints — compliance rule MD-04 |

### Linux depot (`depot_linux.vdf.tpl`)

**Content root:** `steam-content/linux/`

The Linux depot covers x86-64 glibc builds (Ubuntu 22.04 LTS baseline) and
Steam Deck (SteamOS 3.x). Steam Deck Verified tier requires passing the
verification checklist in `docs/STEAM_ROADMAP.md` before the public release
gate (Stage 4).

```
conversation-simulator            # Tauri shell binary
resources/
  bin/
    convsim-core                  # PyInstaller-bundled Python backend
  runtimes/
    llama-server                  # llama.cpp inference server
    whisper-cli                   # Whisper.cpp STT binary
    sherpa-onnx-offline-tts       # Kokoro TTS via sherpa-onnx
  packs/
    job-interview-basic/
    everyday-negotiation/
    language-cafe/
    difficult-conversations/
LICENSE                           # Apache 2.0
NOTICE                            # Third-party licence notices
```

**Excluded by VDF `FileExclusion`:**

| Pattern | Reason |
|---------|--------|
| `*.gguf` | Model weight files — compliance rule MD-04 |
| `*.bin` | Model weight files — compliance rule MD-04 |
| `*.safetensors` | Model weight files — compliance rule MD-04 |
| `*.pt` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.pth` | PyTorch model checkpoints — compliance rule MD-04 |
| `*.ckpt` | Model checkpoints — compliance rule MD-04 |

---

## What players download after first launch

Nothing is downloaded automatically. All post-launch downloads are triggered
only by explicit player action.

### LLM model weights

LLM model weights are **never bundled** in any Steam depot. After first launch
the player is offered a model selection screen. Before any download begins, the
model manager displays all six mandatory disclosure fields (see
[`docs/model-download-policy.md`](../docs/model-download-policy.md)):

1. Model name and family
2. Source URL (HuggingFace Hub)
3. License (SPDX identifier + link to full text)
4. Download size (GB)
5. SHA-256 checksum that will be verified post-download
6. Destination path on the player's machine (`~/.convsim/models/`)

The player must confirm before any bytes are transferred. No model download is
ever triggered by app startup, background update check, or installer script.

### Community and additional scenario packs

In v1 the app ships no in-app community pack browser. Community packs are
distributed outside the app (GitHub, itch.io, direct links) and installed by
the player using the manual import path in the Settings screen. See
[`docs/pack-download-policy.md`](../docs/pack-download-policy.md) for the full
import policy.

---

## Sidecar binary layout and `CONVSIM_BUNDLED_RUNTIME_DIR`

The Tauri shell sets the environment variable `CONVSIM_BUNDLED_RUNTIME_DIR` to
the absolute path of the bundled `runtimes/` directory before launching
`convsim-core`. The Python backend uses this variable to locate sidecar
executables without relying on `PATH`. See
[`docs/sidecar-bundling.md`](../docs/sidecar-bundling.md) for the three-step
resolution order and pseudocode.

All sidecar binaries bind exclusively to `127.0.0.1` (IPv4 loopback). The
`assert_localhost()` guard in `convsim_core/runtime/supervisor.py` enforces
this at every `start()` call and cannot be disabled.

---

## Approved binary payload list

The following executable binary types are approved to appear in Steam depots.
Any other executable binary discovered by `scripts/depot-audit.sh` in the
`[unapproved-binaries]` category causes the audit to fail.

| Binary | Purpose | Approved extension | Notes |
|--------|---------|-------------------|-------|
| Tauri shell | Main app entry point | `.exe` (Windows), none (macOS/Linux) | One per depot |
| `convsim-core` | Python backend | `.exe` (Windows), none (macOS/Linux) | PyInstaller bundle |
| `llama-server` | LLM inference | `.exe` (Windows), none (macOS/Linux) | llama.cpp, loopback only |
| `whisper-cli` | Speech-to-text | `.exe` (Windows), none (macOS/Linux) | Whisper.cpp, loopback only |
| `sherpa-onnx-offline-tts` | Text-to-speech | `.exe` (Windows), none (macOS/Linux) | Kokoro/sherpa-onnx |
| Support DLLs / `.so` files | Runtime dependencies | `.dll` (Windows), `.so` / `.dylib` (POSIX) | Bundled by Tauri/WebView2 and PyInstaller — audited for large ONNX models only |
| Small ONNX voice/VAD models | TTS voice files, VAD | `.onnx` | Maximum 50 MB per file; larger files are rejected |

---

## Audit enforcement

Two complementary mechanisms enforce depot content policy:

### 1. SteamPipe VDF `FileExclusion` patterns

Configured in `steam/depot_*.vdf.tpl`. These exclusions are applied by
SteamPipe before any file is uploaded to Valve's CDN. They act as a final
safety net but are not a substitute for the pre-upload audit.

### 2. `scripts/depot-audit.sh` / `depot-audit.ps1`

Run this script against each platform's content directory before invoking
steamcmd. It catches five categories of prohibited files:

| Category | What it catches |
|----------|----------------|
| `[weights]` | Model weight files by extension and magic-byte detection |
| `[unapproved-binaries]` | Large pickle/numpy files, large ONNX exports, `models/` directories |
| `[devfiles]` | Developer artefacts — `.venv`, `__pycache__`, pytest config, etc. |
| `[secrets]` | Credential files — `.key`, `.pem`, `.pfx`, `config.vdf`, etc. |
| `[fixtures]` | Test fixture directories and files |

The `steam-deploy.yml` workflow runs an additional inline audit step (rule
MD-04) as a belt-and-suspenders check before steamcmd is invoked.

Run the audit locally before a release:

```sh
# Audit Windows depot content
./scripts/depot-audit.sh steam-content/windows

# Audit macOS depot content
./scripts/depot-audit.sh steam-content/macos

# Audit Linux depot content
./scripts/depot-audit.sh steam-content/linux
```

Exit 0 means all audit categories passed. Exit 1 means one or more violations
were found — the depot must not be submitted until all violations are resolved.

---

## Third-party licence notices (`NOTICE`)

The `NOTICE` file at the repository root (and included in every depot at the
depot root) must list all bundled runtimes and their licences before Stage 3
submission. Required entries:

| Component | Licence | Required by |
|-----------|---------|-------------|
| Whisper.cpp | MIT | Risk LI-03 |
| sherpa-onnx / Kokoro TTS | Apache 2.0 | Risk LI-03 |
| llama.cpp | MIT | Risk LI-03 |
| WebView2 (Windows) | Microsoft licence | Risk LI-01 |
| Bundled Python standard library | PSF Licence | Risk LI-01 |

Community-contributed packs loaded by the player carry their own licences and
are not bundled in the depot. See
[`docs/pack-download-policy.md`](../docs/pack-download-policy.md).

---

## Links

- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register; see MD-04
- [`steam/`](../steam/) — SteamPipe VDF templates
- [`scripts/depot-audit.sh`](../scripts/depot-audit.sh) — depot content audit (Linux / macOS)
- [`scripts/depot-audit.ps1`](../scripts/depot-audit.ps1) — depot content audit (Windows PowerShell)
- [`.github/workflows/steam-deploy.yml`](../.github/workflows/steam-deploy.yml) — Steam upload workflow
- [`docs/model-download-policy.md`](../docs/model-download-policy.md) — model download rules
- [`docs/pack-download-policy.md`](../docs/pack-download-policy.md) — pack import policy
- [`docs/sidecar-bundling.md`](../docs/sidecar-bundling.md) — sidecar executable resolution
- [`publishing/STEAM_APP_REGISTRATION.md`](STEAM_APP_REGISTRATION.md) — depot IDs and CI credentials
