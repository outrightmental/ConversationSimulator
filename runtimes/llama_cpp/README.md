<!-- SPDX-License-Identifier: Apache-2.0 -->
# runtimes/llama_cpp

Integration layer for llama.cpp — the primary local LLM runtime.

The llama-server process binds to `http://127.0.0.1:7356` by default.
Runtime logs are written to `~/.convsim/logs/runtime.log`.

## Quickstart

### 1 — Get a llama-server binary

**Option A — Download script**

```sh
# Linux / macOS: the CPU build (on macOS it uses Metal)
./runtimes/llama_cpp/download-runtime.sh
# Binary lands at ~/.convsim/bin/llama-server

# Linux: the Vulkan build, for a graphics card
./runtimes/llama_cpp/download-runtime.sh --variant vulkan
# Binary lands at ~/.convsim/bin/vulkan/llama-server
```

```powershell
# Windows: the CPU build, then the Vulkan build
.\runtimes\llama_cpp\download-runtime.ps1
.\runtimes\llama_cpp\download-runtime.ps1 -Variant vulkan
# Binaries land at $HOME\.convsim\bin\ and $HOME\.convsim\bin\vulkan\
```

The app finds both locations by itself; only the CPU build needs to be on
`PATH` for running `llama-server` by hand. See
[What ships, and the pin](#what-ships-and-the-pin) below.

**Option B — Manual install**

- Download a release from <https://github.com/ggml-org/llama.cpp/releases>
- Extract `llama-server` (or `llama-server.exe` on Windows) and place it in a
  directory on your PATH.

**Option C — Build from source**

```sh
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && cmake -B build && cmake --build build --config Release
# Binary: build/bin/llama-server
```

### 2 — Get a GGUF model

Download a GGUF model file.  The [model registry](../../model-registry/registry.yaml)
lists recommended models.  A starter model (≈2.6 GB):

```
https://huggingface.co/Qwen/Qwen3-4B-Instruct-GGUF
```

### 3 — Start via the sidecar API (managed mode)

```sh
# POST /api/sidecar/start
curl -X POST http://127.0.0.1:7355/api/sidecar/start \
  -H "Content-Type: application/json" \
  -d '{"model_path": "/path/to/model.gguf"}'
```

Optional request fields:

| Field             | Type    | Default       | Description                          |
|-------------------|---------|---------------|--------------------------------------|
| `model_path`      | string  | —             | Absolute path to the GGUF file       |
| `executable`      | string  | auto          | Path to llama-server binary          |
| `host`            | string  | `127.0.0.1`   | Interface for llama-server to bind   |
| `port`            | int     | `7356`        | Port for llama-server to bind        |
| `context_length`  | int     | null          | Context window size (`--ctx-size`)   |
| `threads`         | int     | null          | CPU thread count (`--threads`)       |
| `gpu_layers`      | int     | null          | Layers on the graphics card (`--n-gpu-layers`); leave null so the engine fits them itself |
| `startup_timeout` | float   | 120.0         | Seconds to wait for /health          |

A request that names no `executable`, host, port, context length or thread
count starts the managed engine the way the app does, including the choice
between the graphics card and the processor (see below). Stop with
`POST /api/sidecar/stop`. Query state with `GET /api/sidecar/status`, which
reports the running build as `variant`.

### 4 — External server (advanced)

If you already run your own llama-server, do **not** call `/api/sidecar/start`.
Set the runtime to `llama_cpp` via `POST /api/models/use` — the adapter will
connect to whatever is listening on `CONVSIM_LLAMA_CPP_BASE_URL`
(default `http://127.0.0.1:7356`).

## What ships, and the pin

| Platform | Default build (`runtimes/`) | Vulkan build (`runtimes/vulkan/`) |
|----------|-----------------------------|-----------------------------------|
| Windows x64 | `llama-<tag>-bin-win-cpu-x64.zip` | `llama-<tag>-bin-win-vulkan-x64.zip` |
| Linux x64 (and Steam Deck) | `llama-<tag>-bin-ubuntu-x64.tar.gz` | `llama-<tag>-bin-ubuntu-vulkan-x64.tar.gz` |
| macOS | `llama-<tag>-bin-macos-arm64.tar.gz` (Metal) | none |

The Vulkan archive is the CPU archive plus the Vulkan backend library
(`ggml-vulkan.dll` / `libggml-vulkan.so`; at b9415 every other file is
byte-identical). The two builds are installed in separate directories so the
CPU build never loads that library: ggml loads every backend library beside
the executable and in the working directory, and the app starts the engine
from its own directory. A machine with a broken Vulkan driver therefore starts
the CPU build exactly as before.

`pin.json` is the one pin: the tag and a SHA-256 for every archive the app can
install. `download-runtime.sh`, `download-runtime.ps1`, CI and the packaged
core all read it, and every one of them refuses an archive whose digest is
missing from the pin or does not match it. Upstream publishes no checksum
file, so the digests come from GitHub's release API.

### Which build runs

The app decides at every engine start (issue #531, `engine_variant` in
Settings › Graphics card: Automatic, Graphics card, Processor only):

- **Automatic** runs `llama-server --list-devices` from the Vulkan directory
  and starts the Vulkan build when a discrete card is listed (or a device on
  the measured allow-list in `engine_variant.py`). Integrated graphics alone,
  or no card, starts the CPU build.
- No `--n-gpu-layers` is passed unless the player set one, so the engine fits
  the layers itself to the explicit context size the app already passes.
- If the probe fails, the model does not load, a check request at
  temperature 0 does not continue `1, 2, …, 8,` with `9`, or the engine dies
  during a conversation, the app starts the CPU build, tells the player once,
  and remembers the failure against the graphics adapters, their driver
  versions and the engine, so it does not retry on every start. A driver
  update clears it; so does **Try the graphics card again**.

### Moving the pin

1. Pick the tag and confirm the macOS assets still declare macOS 14.0
   (`scripts/check-macho-minos.py`; see `download-runtime.sh`).
2. Copy every digest from the release API into `pin.json`, one key per line:
   `gh api repos/ggml-org/llama.cpp/releases/tags/<tag> --jq '.assets[] | [.name, .digest] | @tsv'`
   (strip the `sha256:` prefix).
3. Update the asset list pinned in `tests/test_llama_cpp_download.py`.
4. `binary-health-check.yml` downloads every pinned archive and checks it
   against the pin and the pin against the API; the release workflow checks
   that the CPU directory has no Vulkan backend library and that the CPU build
   answers `--list-devices`.

## Error handling

| Situation             | API response                       |
|-----------------------|------------------------------------|
| Port already in use   | 503 `SIDECAR_START_FAILED` with actionable message |
| Executable not found  | 503 `SIDECAR_START_FAILED`         |
| Startup timeout       | 503 `SIDECAR_START_FAILED`         |
| Process crash         | state transitions to `crashed`; check `log_path` |
| Already running       | 409 `SIDECAR_ALREADY_RUNNING`      |

## Log location

`~/.convsim/logs/runtime.log` — contains llama-server stdout/stderr.
Transcript content is **never** written there; only server diagnostic output.

## References

- llama.cpp: <https://github.com/ggml-org/llama.cpp>
- GGUF format: <https://github.com/ggml-org/ggml/blob/master/docs/gguf.md>
- OpenAI-compatible API: `llama-server` exposes `/v1/chat/completions` (SSE streaming)
