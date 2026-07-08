<!-- SPDX-License-Identifier: Apache-2.0 -->
# runtimes/llama_cpp

Integration layer for llama.cpp — the primary local LLM runtime.

The llama-server process binds to `http://127.0.0.1:7356` by default.
Runtime logs are written to `~/.convsim/logs/runtime.log`.

## Quickstart

### 1 — Get a llama-server binary

**Option A — Download script (Linux / macOS)**

```sh
./runtimes/llama_cpp/download-runtime.sh
# Binary lands at ~/.convsim/bin/llama-server
# Follow the printed PATH instructions.
```

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

| Field             | Type    | Default | Description                          |
|-------------------|---------|---------|--------------------------------------|
| `model_path`      | string  | —       | Absolute path to the GGUF file       |
| `executable`      | string  | auto    | Path to llama-server binary          |
| `context_length`  | int     | null    | Context window size (`--ctx-size`)   |
| `threads`         | int     | null    | CPU thread count (`--threads`)       |
| `gpu_layers`      | int     | null    | GPU layers (`--n-gpu-layers`)        |
| `startup_timeout` | float   | 120.0   | Seconds to wait for /health          |

Stop with `POST /api/sidecar/stop`. Query state with `GET /api/sidecar/status`.

### 4 — External server (advanced)

If you already run your own llama-server, do **not** call `/api/sidecar/start`.
Set the runtime to `llama_cpp` via `POST /api/models/use` — the adapter will
connect to whatever is listening on `CONVSIM_LLAMA_CPP_BASE_URL`
(default `http://127.0.0.1:7356`).

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
