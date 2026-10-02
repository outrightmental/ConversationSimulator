---
title: "Sidecar bundling"
description: "How each ConversationSimulator sidecar locates its executable in developer builds and packaged Steam builds."
sidebar:
  order: 10
---

ConversationSimulator runs four managed subprocess sidecars alongside the core
Python service. This document explains how each sidecar locates its executable
in developer builds and in packaged Steam builds.

| Sidecar | Service name | Default port | Runtime id |
|---------|-------------|-------------|------------|
| llama.cpp | `convsim-llm` | 7356 | `llama_cpp` |
| Whisper.cpp (STT) | `convsim-stt` | 7357 | `whisper_cpp` |
| Kokoro / sherpa-onnx (TTS) | `convsim-tts` | 7358 | `kokoro` |
| Silero VAD | _(in-process)_ | — | `silero_vad` |

All sidecars must bind only to `127.0.0.1` (IPv4 loopback) or `::1` (IPv6
loopback). The `assert_localhost()` guard in
`convsim_core/runtime/supervisor.py` enforces this at every `start()` call.
See [network-security.md](/trust/network-security/) for the localhost-only policy.

---

## Executable resolution order

Each sidecar resolves its binary in this order, stopping at the first hit:

1. **Explicit override** — the environment variable `CONVSIM_<SIDECAR>_EXECUTABLE`
   (e.g. `CONVSIM_LLAMA_CPP_EXECUTABLE`), or the `executable` field in the
   `POST /api/sidecar/start` request body.
2. **Bundled path** — a platform-specific directory adjacent to the application
   binary (Steam builds only; see below).
3. **PATH lookup** — `shutil.which("llama-server")` or the equivalent name for
   each sidecar (developer builds only).

If none of the above resolves, `start()` raises `RuntimeError` with an
actionable message directing the user to install the missing binary.

---

## Developer builds

In a developer build the application is started directly from the repository
(`uvicorn convsim_core.app:app` or `python -m convsim_core`). Sidecar
binaries are expected to be on the developer's `PATH`.

**Install sidecars for development:**

```sh
# llama.cpp (llama-server)
./runtimes/llama_cpp/download-runtime.sh
# → binary at ~/.convsim/bin/llama-server; add to PATH

# Whisper.cpp
./runtimes/whisper_cpp/download-runtime.sh
# → binary at ~/.convsim/bin/whisper-cli; add to PATH

# Kokoro / sherpa-onnx
./runtimes/kokoro/download-runtime.sh
# → binary at ~/.convsim/bin/sherpa-onnx-offline-tts; add to PATH
```

You can also set the explicit override variable to point to any binary:

```sh
export CONVSIM_LLAMA_CPP_EXECUTABLE=/path/to/llama-server
```

---

## Steam (packaged) builds

In a Steam build the application executable and all sidecars are bundled inside
the Steam depot under a known relative layout. The Tauri/Electron wrapper
sets the environment variable `CONVSIM_BUNDLED_RUNTIME_DIR` to the absolute
path of the `runtimes/` directory inside the installed depot before launching
`convsim-core`.

### Bundled directory layout

```
<steam-install-dir>/
├── convsim               # main application executable (Tauri shell)
└── runtimes/
    ├── llama-server      # llama.cpp inference server
    ├── whisper-cli       # Whisper.cpp transcription binary
    └── sherpa-onnx-offline-tts   # Kokoro TTS binary
```

On Windows the binaries include the `.exe` suffix. On macOS and Linux there is
no suffix. The bundled path resolver appends the correct suffix for the current
platform automatically.

### Bundled path lookup (Python pseudocode)

```python
import os
import sys
from pathlib import Path

def find_sidecar_executable(env_key: str, binary_name: str) -> str | None:
    """Resolve a sidecar binary using the Steam bundling convention.

    ``env_key`` is the override variable keyed on the sidecar id, e.g.
    ``CONVSIM_LLAMA_CPP_EXECUTABLE`` for the ``llama_cpp`` sidecar.
    ``binary_name`` is the on-disk filename, e.g. ``llama-server``.
    """
    # 1. Explicit env-var override always wins.
    if override := os.environ.get(env_key):
        return override

    # 2. Bundled path (Steam builds).
    bundled_dir = os.environ.get("CONVSIM_BUNDLED_RUNTIME_DIR")
    if bundled_dir:
        suffix = ".exe" if sys.platform == "win32" else ""
        candidate = Path(bundled_dir) / f"{binary_name}{suffix}"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    # 3. PATH (developer builds).
    import shutil
    return shutil.which(binary_name)
```

The actual implementation lives in each sidecar's module
(`find_executable()` in `convsim_core/runtime/sidecar.py` for llama.cpp, which
resolves `CONVSIM_LLAMA_CPP_EXECUTABLE` → `CONVSIM_BUNDLED_RUNTIME_DIR/llama-server`
→ PATH).

---

## Localhost enforcement in packaged builds

`assert_localhost(host)` in `convsim_core/runtime/supervisor.py` is called at
the top of every sidecar `start()` method. It raises `RuntimeError` if the
requested bind host is not `127.0.0.1`, `::1`, or `localhost`. This check
cannot be disabled at runtime — there is no environment variable or config
flag to bypass it. Network binding is always localhost-only.

---

## Adding a new sidecar

When implementing a new sidecar (e.g. `WhisperCppSidecar`):

1. Inherit from `SidecarProcess` in `convsim_core/runtime/supervisor.py`.
2. Implement `sidecar_id`, `display_name`, `stop()`, and `get_status()`.
3. Add a typed `start()` method that calls `assert_localhost(host)` before
   spawning the child process.
4. Implement executable resolution using the three-step order described above:
   `CONVSIM_<SIDECAR_ID>_EXECUTABLE` override → the bundled binary under
   `CONVSIM_BUNDLED_RUNTIME_DIR` → PATH.
5. Register the sidecar with `ProcessSupervisor` in `app.py`'s `lifespan`.
6. Add tests covering: missing binary, port conflict, crash, restart, and
   graceful shutdown. See `tests/test_sidecar.py` for the llama.cpp reference
   implementation.

---

## The core itself is a sidecar of the desktop shell

Everything above is about sidecars that `convsim-core` manages. One level up,
`convsim-core` is itself a managed child of the Tauri desktop shell: a single
PyInstaller executable packaged into the installer, which is what lets a player
install one artifact and reach the Welcome screen with no terminal involved.

The shell resolves it in the same four-step order used above
(`CONVSIM_CORE_EXECUTABLE` → `CONVSIM_BUNDLED_RUNTIME_DIR` → the Tauri resource
directory → PATH), and hands it `CONVSIM_HOST`, `CONVSIM_PORT`,
`CONVSIM_DATA_ROOT`, `CONVSIM_APP_VERSION`, the edition, and
`CONVSIM_BUNDLED_RUNTIME_DIR` — the last being how the sidecars in the table
above are found in a packaged build.

Two parts of that lifecycle matter to those sidecars:

- **Readiness** is `GET /api/health`, not an open TCP port. An open port only
  says *something* is on 7355; the health body is what proves it is a
  convsim-core — and therefore that the sidecar supervisor this document
  describes exists at all.
- **Shutdown** is SIGTERM, not SIGKILL (`taskkill /T` on Windows). Only a signal
  the engine can handle lets uvicorn run the lifespan shutdown, and that shutdown
  is where `ProcessSupervisor.stop_all()` stops every sidecar in the table. A
  hard kill of the engine orphans all of them — llama-server keeps a model
  resident in RAM and keeps port 7356.

A crash is the same event without the choice: an engine that died never reached
its lifespan shutdown either, so every sidecar in the table above survives it.
The desktop shell restarts the engine (see "Crash restart" in
`apps/desktop/README.md`), and the replacement's `ensure_llama_sidecar_running`
then fails `_is_port_in_use` against the orphan still holding 7356. Inference
usually keeps working anyway — `LlamaCppRuntime` reaches llama-server over HTTP
at its configured `base_url` and does not care which process started it, so
`runtime.health()` and `/v1/chat/completions` both land on the orphan — but the
engine no longer *owns* that process: `sidecar_diagnostics` reports
`port_conflict`, and anything that has to restart it (`/api/models/use`, a model
switch) fails until the orphan is gone.

Nothing in the product removes it. Relaunching does not: `stop_all()` stops the
sidecars a *registered* sidecar object holds a `self._process` for, and the
replacement engine's llama-server sidecar never started one. Neither does the
shell's teardown: on Unix it signals the engine pid, and on Windows
`taskkill /T` walks the tree below the pid it is given — the orphan's parent is
the engine that died, so it is in neither. It has to be ended by hand. Giving
the engine its own process group (Unix) or job object (Windows) would hand the
shell a handle on the whole subtree; that is a larger change than the one this
document describes and is not made today.

---

## Environment variable reference

| Variable | Purpose |
|---|---|
| `CONVSIM_BUNDLED_RUNTIME_DIR` | Absolute path to the bundled `runtimes/` directory (set by the Tauri/Electron wrapper in Steam builds) |
| `CONVSIM_LLAMA_CPP_EXECUTABLE` | Override path to `llama-server` |
| `CONVSIM_WHISPER_CPP_BINARY_PATH` | Override path to `whisper-cli` |
| `CONVSIM_KOKORO_EXECUTABLE` | Override path to `sherpa-onnx-offline-tts` |
| `CONVSIM_CORE_EXECUTABLE` | Override path to the `convsim-core` binary the desktop shell starts |

---

## Related documents

- [network-security.md](/trust/network-security/) — localhost-only binding policy
- [runtime-adapters.md](/reference/runtime-adapters/) — ChatRuntime interface and built-in adapters
- [architecture.md](/reference/architecture/) — service topology and port assignments
- [runtimes/llama_cpp/README.md](https://github.com/outrightmental/ConversationSimulator/blob/main/runtimes/llama_cpp/README.md) — llama.cpp setup
