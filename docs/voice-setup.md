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

An engine can also be satisfied without the app locating it: the Kokoro command
the plan hands out runs the server in Docker, which puts no `kokoro-server`
binary on `PATH`. When the worker reports the capability ready and
`_engine_location` finds nothing, the plan marks the row `serving` — reported
`installed`, with no `found_at` — and the screen says "already running" instead
of re-offering a command the player has just run or a **Start** button that
would only collide on the port.

The plan is re-read on window focus. The two native engines are installed
*outside* the app, so a player who runs `brew install whisper.cpp` in a
terminal and switches back sees the row tick over without a reload.

### The microphone row

The last row of the speech section is the one piece no download can satisfy.
The browser has to be granted microphone access, so the row asks for it
(`useMicCapture.requestPermission`) and names the way back from a denial —
`navigator.permissions` reporting `denied` is otherwise a silent dead end
discovered mid-conversation.

Once the plan reports `stt.ready`, the same row offers **Record a test
phrase**: one real round trip through `POST /api/stt/upload` — microphone,
`ffmpeg`, whisper model — with the transcript repeated back. Installing the
pieces does not prove the chain works end to end, and the first turn of a
scenario is the wrong place to find that out. A failure names the likely
culprit rather than reporting "unavailable": an `error` status points at
`ffmpeg`, an empty transcript at mic placement.

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
| `whisper-cli` | whisper.cpp publishes no checksummed binary for every platform. llama.cpp's release carries a `sha256sum.txt`; whisper.cpp's does not, and shipping an unverified binary is worse than handing over the install command. |
| Kokoro TTS server | Steam depot builds bundle it (`CONVSIM_BUNDLED_RUNTIME_DIR`). Elsewhere the official container image is the shortest path. |

Only Homebrew packages whisper.cpp. There is no winget package for it —
winget-pkgs carries `ggml.llamacpp` and nothing else from that publisher — and
the common apt repositories do not ship it either, so Linux and Windows get the
upstream `cmake` build instead of a package-manager one-liner.

| Platform | Command | Follow-up |
|----------|---------|-----------|
| macOS | `brew install whisper.cpp` | None — brew puts `whisper-cli` on `PATH`. (`whisper-cpp` is a deprecated oldname that still resolves but warns.) |
| Linux | `git clone` + `cmake --build`, then `sudo cp build/bin/whisper-cli /usr/local/bin/` | None — the command ends by copying onto `PATH`. |
| Windows | `git clone` + `cmake --build` | Required: the binary stays in `build\bin\Release`, and the app must be restarted. |

A command that cannot finish the job carries a `command_notes` entry for that
platform, which the plan returns as `command_note` and the screen renders in
amber under the command block. Windows is the only case today: the build leaves
`whisper-cli.exe` in the build tree, so the note names the two routes the worker
honours — put that folder on `PATH`, or set
`CONVSIM_WHISPER_CPP_BINARY_PATH` to the `.exe`. Without it the player runs a
command, nothing changes, and they are back at the dead end this flow exists to
remove.

Both of those routes need an app restart, and the note says so. `PATH` and the
environment are a snapshot taken when a process starts, so **Check again** —
which re-runs the same `shutil.which` lookup inside the already-running service
— cannot see either change. `brew install` needs no restart because it installs
onto a `PATH` entry the running process already has; building from source does
not.

Windows players who would rather not build can take `whisper-bin-x64.zip` from
a `bNNNN` tag on the [whisper.cpp releases
page](https://github.com/ggml-org/whisper.cpp/releases) and put `whisper-cli.exe`
on `PATH`; those zips carry no published checksum, which is exactly why the app
will not fetch them for you.

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
| The `voice-ready` preflight warning's fix action | Whenever a voice component is unavailable (full edition; the demo refuses the flow, so its remedy stays on Settings) |

---

## Links

- [Speaking and listening](https://docs.conversationsimulator.com/play/voice/) — the published player-facing walkthrough (`docs-site/src/content/docs/play/voice.md`)
- [`docs/model-download-policy.md`](model-download-policy.md) — the rules voice assets inherit
- [`runtimes/whisper_cpp/README.md`](../runtimes/whisper_cpp/README.md) — STT engine reference
- [`runtimes/kokoro/README.md`](../runtimes/kokoro/README.md) — TTS server reference
- [`runtimes/silero_vad/README.md`](../runtimes/silero_vad/README.md) — VAD reference
- [`docs/voice-smoke-tests.md`](voice-smoke-tests.md) — manual verification of the voice path
