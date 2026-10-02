<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Voice Setup

> **Purpose:** Describe the in-app flow that installs speech-to-text and the
> NPC voice, the assets it downloads, and the engines it deliberately does not.
>
> **Scope:** The `/voice-setup` screen and the `/api/voice/setup/*` endpoints.
> Model-weight rules follow [`docs/model-download-policy.md`](model-download-policy.md);
> this document covers only what is specific to voice.

---

## 1. Why there is a flow at all

The app is fully playable in text. Voice is optional, and the pieces it needs
are not all of the same kind:

| Kind | Examples | Can the app install it? |
|------|----------|-------------------------|
| **Weight file** | whisper.cpp GGML model, Silero VAD ONNX model | **Yes** — downloaded and SHA-256 verified |
| **Native engine** | `whisper-cli`, the Kokoro TTS server | **No** — neither publishes a checksummed cross-platform release |
| **Python extra** | `onnxruntime` | No — guidance only |
| **System tool** | `ffmpeg` | No — guidance only |

Settings used to report `STT: Not installed` and stop, which left the only
route to voice buried in `runtimes/*/README.md`. The flow exists so the first
kind is a button and the second kind is a copyable one-line command plus a
re-check, rather than a docs hunt.

## 2. What the screen does

`/voice-setup` renders `GET /api/voice/setup/plan` as a checklist, one section
per capability:

| Capability | Needs | Optional? |
|------------|-------|-----------|
| **Speak your turns** (`stt`) | `whisper-cli` + one whisper model | No — gates all voice input |
| **Hear the NPC** (`tts`) | The Kokoro server | No — gates spoken NPC replies |
| **Hands-free turn-taking** (`vad`) | Silero VAD model + `onnxruntime` | Yes — push-to-talk works without it |

Each row carries its own next action: a download, a platform-specific install
command with a **Check again** button, or — for a Kokoro binary that exists but
is not running — a **Start the voice server** button.

The plan is re-read on window focus. The two native engines are installed
*outside* the app, so a player who runs `brew install whisper-cpp` in a
terminal and switches back sees the row tick over without a reload.

## 3. Downloadable assets

The catalogue lives in
[`convsim_core/services/voice_registry.py`](../services/convsim-core/convsim_core/services/voice_registry.py)
as `VOICE_ASSETS`.

| Asset id | Capability | Size | Licence | Source |
|----------|-----------|------|---------|--------|
| `whisper-tiny-en` | STT | 74 MB | MIT | `ggerganov/whisper.cpp` |
| `whisper-base-en` | STT (recommended) | 141 MB | MIT | `ggerganov/whisper.cpp` |
| `whisper-base` | STT (multilingual) | 141 MB | MIT | `ggerganov/whisper.cpp` |
| `whisper-small-en` | STT | 465 MB | MIT | `ggerganov/whisper.cpp` |
| `silero-vad` | VAD (recommended) | 2.2 MB | MIT | `snakers4/silero-vad` |

Rules, all enforced by `tests/test_voice_setup.py`:

- **Every entry carries a SHA-256.** There is no unverified-download path. A
  file that does not match is deleted, never installed.
- **Every URL is revision-pinned** to a commit SHA, so a moved tag cannot
  change the bytes a checksum was recorded against. The Silero pin is
  additionally load-bearing: that revision ships the v5 model whose
  `(input, state, sr)` signature `convsim_core/vad/silero.py` drives.
- **Exactly one asset per capability is `recommended`** — the one the
  one-click path installs.

The whisper weights come from `ggerganov/whisper.cpp` on Hugging Face. The
`ggml-org/whisper.cpp` URL that older runtime docs used answers `401`.

### Where assets land

Downloads go where the engine that consumes them actually looks, resolved from
the worker's own configuration (so `CONVSIM_WHISPER_CPP_MODEL_PATH` and
`CONVSIM_SILERO_VAD_MODEL_PATH` are honoured):

- **STT** — the upstream filename inside the directory of the configured STT
  model path. The player may install more than one and switch between them.
- **VAD** — the exact configured VAD model path. There is only one VAD model,
  so any other filename would simply never be read.

Because the installed STT file is not always the configured default, a
completed STT install persists its path to `user_settings.stt_model_path` and
re-points the live worker. App startup re-applies it, so the choice survives a
restart.

## 4. Engines the app will not download

| Engine | Why manual |
|--------|-----------|
| `whisper-cli` | whisper.cpp publishes no checksummed binary for every platform. llama.cpp's release carries a `sha256sum.txt`; whisper.cpp's does not, and shipping an unverified binary is worse than one command. |
| Kokoro TTS server | Steam depot builds bundle it (`CONVSIM_BUNDLED_RUNTIME_DIR`). Elsewhere the official container image is the shortest path. |

The plan returns the command for the caller's platform (`sys.platform`,
normalised so `linux2`-style values still resolve). Kokoro is the only
`startable` engine: when the binary resolves but the sidecar is stopped,
`POST /api/voice/setup/engine/kokoro-server/start` launches it and the
capability flips to ready without leaving the screen.

## 5. Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/voice/setup/plan` | Capabilities, assets, engines, and the machine's current state |
| `POST` | `/api/voice/setup/install` | Start a download job for the named assets (defaults to the recommended set) |
| `GET` | `/api/voice/setup/install/{id}` | Poll per-asset byte progress |
| `DELETE` | `/api/voice/setup/install/{id}` | Cancel a running job |
| `POST` | `/api/voice/setup/engine/{id}/start` | Start a startable engine |

All of them are full-edition only; the demo refuses them server-side.

### Download behaviour

Downloads stream to `<dest>.part`, verify SHA-256, then promote. Cancel, a
transport error and a checksum mismatch all remove the partial file, so an
unverified byte is never visible to an engine. Only a *killed process* leaves a
`.part` behind, and the next attempt resumes it with an HTTP `Range` request
(falling back to a clean restart if the server answers `200`). A job left
non-terminal by a kill is retired at startup rather than re-driven — the plan
already reflects whatever landed, and one button fetches the rest.

Network access goes through `NetworkMode.EXPLICIT_DOWNLOAD`, the same gate as
LLM weights, so nothing here is reachable from play-mode code. A cancelled job
is recorded as `cancelled`, never `failed`, so the UI can tell a user abort
from a real error.

## 6. Where the flow is entered

| From | When |
|------|------|
| Settings → Voice readiness | Always (header CTA), plus an install link on each component that is not ready |
| Home → STT / TTS status badge | While that component is not installed |
| Debrief → "Next time, say it out loud" | After the first real conversation |

---

## Links

- [`docs/model-download-policy.md`](model-download-policy.md) — the rules voice assets inherit
- [`runtimes/whisper_cpp/README.md`](../runtimes/whisper_cpp/README.md) — STT engine reference
- [`runtimes/kokoro/README.md`](../runtimes/kokoro/README.md) — TTS server reference
- [`runtimes/silero_vad/README.md`](../runtimes/silero_vad/README.md) — VAD reference
- [`docs/voice-smoke-tests.md`](voice-smoke-tests.md) — manual verification of the voice path
