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
| **Python extra** | `onnxruntime` | No — guidance, and only in a source checkout |
| **System tool** | `ffmpeg` | No — guidance only (but required: it decodes the browser's recording) |

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

There is also a **Check again** button beside the "N of M voice features ready"
line, always on the page. A row's own **Check again** is offered only while its
engine is *missing*, which is the wrong half of the cases: the commonest reply
from the start endpoint is "already starting — press Check again shortly", and
by then the Kokoro binary has resolved and that row's button is gone. The rows
that never had one (`ffmpeg`, `onnxruntime`, a model dropped in by hand) need it
too, and a focus re-read only reaches a player who actually left the window.

A re-read — **Check again**, or that return to the window — also clears the last
engine-start message (`useVoiceSetup.recheck`). Asking where things stand now
must not leave *where they stood then* above the answer: the commonest reply from
the start endpoint is "already starting, press Check again shortly", and the
Check again it asks for may well find the server up.

`ffmpeg` is its own row for the same reason, with the same caveat on Windows:
`winget` writes the install folder into the user `PATH`, which the already
running service never re-reads, so that row asks for a restart too. The Linux
command is `sudo apt install ffmpeg`, which is Debian's and Ubuntu's and nobody
else's, so a note under it names `dnf` and `pacman` — the Steam Deck runs
Arch-based SteamOS, and a command that answers "command not found" there is the
same dead end as a winget package that does not exist.

That row is not a nice-to-have. `whisper-cli` decodes its input with miniaudio
(WAV, FLAC, MP3, Ogg Vorbis) and reaches for `ffmpeg` only when it was compiled
with `WHISPER_FFMPEG` — which neither Homebrew's formula nor the source builds
above enable. The browser records WebM/Opus, which miniaudio cannot read, so
`WhisperCppWorker` transcodes every non-WAV upload to 16 kHz mono 16-bit WAV
with `ffmpeg` before `whisper-cli` is invoked. Without `ffmpeg` no browser
recording can be transcribed, whatever else is installed, so the worker raises
`SttUnavailableError` naming it rather than letting `whisper-cli` answer
"failed to read audio data".

`ffmpeg` is located with the same `find_tool` lookup as `whisper-cli` — `PATH`
first, then the package-manager prefixes — and the worker spawns the *resolved
path*, not the bare name. Both halves matter on macOS: `brew install ffmpeg` is
what the ffmpeg card hands out there, and a lookup that found Homebrew's copy
only to spawn `"ffmpeg"` out of launchd's `PATH` would report the row green and
then fail every utterance. The same resolution is used by the Silero VAD
worker, so hands-free cannot fail on a recording the screen has just reported
`ffmpeg` as present for.

### Hands-free in a packaged build

`onnxruntime` is the `vad` extra in `services/convsim-core/pyproject.toml`, and
the release PyInstaller build installs only `[build]` — so no shipped binary
contains it, and `pip` is in the spec's `excludes`. `pip install onnxruntime`
therefore cannot reach a packaged server: there is no interpreter for it to
install into. The plan reports this as `onnxruntime_installable: false` and the
screen replaces the command with the reason, because a command that can never
turn its row green is the dead end this flow exists to remove. Hands-free needs
a source checkout with the extra installed; push-to-talk covers every scenario
either way.

`default_asset_ids()` drops the Silero model from the one-click set in the same
case, for the same reason: disclosing, charging for and fetching 2.2 MB for the
one capability the row above reports as impossible here is that dead end in
download form. A source checkout *without* the extra still gets it, because
there the `pip` command is offered and the model is a step on a route that goes
somewhere. The asset keeps its own row either way — it genuinely is not
installed — and a hand-written `POST` naming it is still honoured; only the
recommendation changes.

### The microphone row

The last row of the speech section is the one piece no download can satisfy.
The browser has to be granted microphone access, so the row asks for it
(`useMicCapture.requestPermission`, which reads the answer off the
`getUserMedia` rejection rather than querying `navigator.permissions`) and names
the way back from a denial — a blocked microphone is otherwise a silent dead end
discovered mid-conversation.

Once the plan reports `stt.ready`, the same row offers **Record a test
phrase**: one real round trip through `POST /api/stt/upload` — microphone,
`ffmpeg`, whisper model — with the transcript repeated back. Installing the
pieces does not prove the chain works end to end, and the first turn of a
scenario is the wrong place to find that out. A failure names the likely
culprit rather than reporting "unavailable": a missing `ffmpeg` is named
outright, an `error` status points at the model, an empty transcript at mic
placement.

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
| `whisper-cli` | whisper.cpp publishes no checksummed binary for every platform. llama.cpp's release carries a `sha256sum.txt`; whisper.cpp's does not, and shipping an unverified binary is worse than handing over the install command. Steam depot builds do bundle it (`CONVSIM_BUNDLED_RUNTIME_DIR`), so there the row resolves with nothing to install. |
| Kokoro TTS server | Steam depot builds bundle it (`CONVSIM_BUNDLED_RUNTIME_DIR`). Elsewhere the official container image is the shortest path — for anyone who has Docker, which the row checks for and names when it is absent. |

### Where `whisper-cli` is looked for

`find_whisper_binary` delegates to `convsim_core.stt.whisper_cpp._find_binary`,
so the plan can never report an engine the worker would then fail to find. That
lookup follows the same sidecar resolution convention as `llama-server` and
the Kokoro server (`docs/sidecar-bundling.md`):

1. `CONVSIM_WHISPER_CPP_BINARY_PATH` — explicit override, and a dead end by
   design: an override pointing at nothing reports *missing* rather than
   falling through to the steps below, so onboarding never shows a green row
   for a path that cannot be executed, and never quietly transcribes with a
   different binary than the one that was configured.
2. `<CONVSIM_BUNDLED_RUNTIME_DIR>/whisper-cli[.exe]` — Steam depot builds ship
   the binary in `runtimes/` and hand the backend that variable instead of
   editing `PATH` (`publishing/STEAM_DEPOT_CONTENTS.md`). A `PATH`-only lookup
   reported speech-to-text missing on the one platform that bundles it, and
   this flow would then have handed those players a from-source `cmake` build
   for a program already installed one directory away — on an immutable SteamOS
   root, no less.
3. `~/.convsim/bin/whisper-cli[.exe]` — the per-user install directory, the
   same one `llama-server` resolves from. This is the destination both build
   commands below aim at.
4. `PATH`, then the package-manager bin directories a GUI-launched process
   does not inherit — `/opt/homebrew/bin`, `/usr/local/bin`, `/opt/local/bin`
   on macOS; `/usr/local/bin` and `/home/linuxbrew/.linuxbrew/bin` on Linux
   (`convsim_core/runtime/toolpath.py`). macOS needs this step and Windows does
   not: launchd hands every GUI app `/usr/bin:/bin:/usr/sbin:/sbin` and the
   Tauri shell passes its environment through untouched, so a Finder- or
   Steam-launched build cannot see anything `brew install` put on disk —
   including the `whisper-cli` that `brew install whisper.cpp`, the command
   *this flow hands out*, has just installed. Windows keeps the machine `PATH`
   in every process environment, GUI ones included.

Steps 2–4 are re-resolved on **every** plan read and every health check, so
dropping the binary into either directory turns the row green on the next
**Check again** with no restart. Only step 1 — a new environment variable — is
a process-start snapshot, which is why no note asks the player to set one.

Only Homebrew packages whisper.cpp. There is no winget package for it —
winget-pkgs carries `ggml.llamacpp` and nothing else from that publisher — and
the common apt repositories do not ship it either, so Linux and Windows get the
upstream `cmake` build instead of a package-manager one-liner.

| Platform | Command | Note under it |
|----------|---------|---------------|
| macOS | `brew install whisper.cpp` | None once it runs — step 4 of the lookup above searches Homebrew's bin directory, so the row clears without a `PATH` edit. When `brew` is *not* on this machine: how to get Homebrew, and that the source build is the alternative. (`whisper-cpp` is a deprecated oldname that still resolves but warns.) |
| Linux | `git clone` + `cmake --build -DBUILD_SHARED_LIBS=OFF`, then `cp build/bin/whisper-cli ~/.convsim/bin/` | Toolchain: `git`, `cmake`, a C++ compiler. Then **Check again**; no restart. |
| Windows | `git clone` + `cmake --build -DBUILD_SHARED_LIBS=OFF`, as three separate lines | Toolchain as above, plus: copy `whisper-cli.exe` out of `build\bin\Release` into `.convsim\bin`. Then **Check again**; no restart. |

Three details in that table are load-bearing.

**`-DBUILD_SHARED_LIBS=OFF`.** Upstream defaults it ON everywhere but MinGW,
and that build drops `libwhisper`/`libggml` beside the executable in
`build/bin` and links against them through a build-tree rpath. The install step
copies *only* `whisper-cli` out of the tree, so deleting the clone — the
obvious tidy-up once the binary is "installed" — would leave something the
lookup still finds and `whisper-cli` can no longer load. The plan would report
the engine present, the row would be green, and the failure would surface
mid-conversation. A static link makes the one file the whole install, and lets
the player delete the source tree.

**`~/.convsim/bin` rather than `/usr/local/bin`.** It needs no `sudo`, an
immutable SteamOS root offers no route into `/usr/local` at all, and because it
is step 3 of the lookup above, **Check again** works there. A `PATH` edit would
have needed a restart instead.

**Newlines instead of `&&` on Windows.** PowerShell gained `&&` in version 7;
Windows PowerShell 5.1, the shell a stock Windows install opens, answers the
chained line with "The token '&&' is not a valid statement separator in this
version" and runs none of it — the same dead end as a package name that 404s.
A newline is a statement separator in both PowerShell and `cmd.exe`, so the
three build steps are handed over on three lines and the screen renders the
command block `pre-wrap`. For the same reason the Windows copy step is prose in
the note rather than a fourth line: the destination is under the user's home
directory, which `cmd.exe` spells `%USERPROFILE%` and PowerShell spells
`$env:USERPROFILE`, so no single command string is right in both.

A command that cannot finish the job on its own carries a note, which the plan
returns as `command_note` and the screen renders in amber under the command
block. Two kinds share that slot, and `engine_command_note` resolves them in
this order:

1. **A per-platform caveat** (`command_notes[platform]`): a prerequisite the
   command needs, or a step it cannot perform for itself. Both whisper.cpp
   source builds declare one — `git`, `cmake` and a C++ compiler, none of which
   the app bundles, plus the copy step on Windows. Saying nothing would send
   the player to a terminal to meet `git: command not found`, which is the dead
   end this screen exists to remove.
2. **A missing prerequisite the command runs** (`requires_tool` +
   `requires_tool_note`), reported only when `find_tool` cannot find it — the
   same `PATH`-then-package-manager-prefixes lookup as above, and for the same
   reason: `shutil.which` alone would tell a Finder-launched macOS build that
   the `brew` which installed everything on the machine "was not found". So the
   row is silent for anyone who already has the program. Two commands qualify:
   Kokoro's container command, which without Docker answers `docker: command
   not found`, and whisper.cpp's macOS one-liner, which without Homebrew
   answers `brew: command not found`. Homebrew is not part of macOS, so a stock
   Mac meets that; each note names the program *and* the alternative route
   (run the server directly; build whisper.cpp from source).

`whisper-cli` declares both, which makes the precedence load-bearing rather
than a tiebreak: its `requires_tool` belongs only to the macOS command, and the
two source-build platforms carry a `command_notes` entry that wins there — so
no brew note reaches the platforms whose commands never run brew.

Windows players who would rather not build can take `whisper-bin-x64.zip` from
a `bNNNN` tag on the [whisper.cpp releases
page](https://github.com/ggml-org/whisper.cpp/releases) and drop
`whisper-cli.exe` into the same `.convsim\bin` folder; those zips carry no
published checksum, which is exactly why the app will not fetch them for you.

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
(falling back to a clean restart if the server answers `200`). A `.part` that
already hashes to the expected value is promoted without a request at all: the
kill can land after the last byte and before the rename — the hashing of a
150 MB model is seconds of that window — and `bytes=<size>-` would then draw a
`416` and fail a download that had in fact finished. A job left
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
| The conversation brief's voice rows | While STT or TTS is unavailable — the moment the player is choosing an input mode and finds the spoken ones greyed out |
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
